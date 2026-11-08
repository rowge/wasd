// Write a KDE wallet file without a dialog.
// The public KWallet open call asks the user to create a wallet when the
// file is missing. Completing the install writes that file first, and only
// when Set a password was left unchecked.
#include <kwalletbackend.h>

#include <gpgme++/context.h>
#include <gpgme++/data.h>
#include <gpgme++/decryptionresult.h>
#include <gpgme++/global.h>
#include <gpgme++/key.h>
#include <gpgme++/keylistresult.h>

#include <QDBusConnection>
#include <QDBusMessage>
#include <QCoreApplication>
#include <QByteArray>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QString>
#include <QVariant>

#include <openssl/crypto.h>
#include <openssl/evp.h>

#include <QList>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>

namespace {

constexpr int kMissing = -1;
constexpr int kUnreadable = -2;
constexpr int kCipherGpg = 2;

void wipe(QByteArray &bytes)
{
    if (bytes.isDetached() == false)
        bytes.detach();
    if (!bytes.isEmpty())
        OPENSSL_cleanse(bytes.data(), size_t(bytes.size()));
    bytes.fill('\0');
    bytes.clear();
}

struct Secret {
    QByteArray bytes;
    ~Secret()
    {
        wipe(bytes);
    }
};

QString textOf(const char *value)
{
    return QString::fromLatin1(value ? value : "");
}

QString textOf(const std::string &value)
{
    return QString::fromStdString(value);
}

bool validFingerprint(const QString &fingerprint)
{
    if (fingerprint.size() != 40 && fingerprint.size() != 64)
        return false;
    for (const QChar character : fingerprint) {
        const char ascii = character.toLatin1();
        const bool hex = (ascii >= '0' && ascii <= '9')
            || (ascii >= 'a' && ascii <= 'f')
            || (ascii >= 'A' && ascii <= 'F');
        if (!hex)
            return false;
    }
    return true;
}

struct WalletPaths {
    QString file;
    QString backup;
    QString salt;
};

WalletPaths walletPaths()
{
    WalletPaths paths;
    const QString dir = KWallet::Backend::getSaveLocation();
    const QString name = KWallet::Backend::encodeWalletName(QStringLiteral("kdewallet"));
    paths.file = dir + QLatin1Char('/') + name + QStringLiteral(".kwl");
    paths.backup = paths.file + QStringLiteral(".wasd-old");
    paths.salt = dir + QLatin1Char('/') + name + QStringLiteral(".salt");
    return paths;
}

int headerCipher(const QString &path)
{
    const QFileInfo info(path);
    if (!info.exists() || info.size() < 60)
        return kMissing;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return kUnreadable;
    char buffer[16];
    if (file.read(buffer, 16) != 16)
        return kUnreadable;
    const char magic[] = {'K', 'W', 'A', 'L', 'L', 'E', 'T', '\n', '\r', '\0', '\r', '\n'};
    if (std::memcmp(buffer, magic, 12) != 0)
        return kUnreadable;
    return static_cast<unsigned char>(buffer[14]);
}

bool blowfishCipher(int cipher)
{
    return cipher == 0 || cipher == 3;
}

int prepareCreate(const WalletPaths &paths)
{
    const QFileInfo wallet(paths.file);
    const QFileInfo backup(paths.backup);
    const bool walletReady = wallet.exists() && wallet.size() >= 60;
    const bool backupReady = backup.exists() && backup.size() >= 60;
    if (!walletReady && backupReady) {
        QFile::remove(paths.file);
        if (!QFile::rename(paths.backup, paths.file))
            return 1;
        std::fprintf(stderr, "The wallet backup was restored.\n");
        return 4;
    }
    if (walletReady) {
        std::fprintf(stderr, "The wallet file is already there.\n");
        return 1;
    }
    if (wallet.exists())
        QFile::remove(paths.file);
    return 0;
}

void gpgmeOnce()
{
    static bool ready = false;
    if (!ready) {
        GpgME::initializeLibrary();
        ready = true;
    }
}

QString fingerprintFor(const QString &keyId)
{
    const QString wanted = keyId.toLower();
    if (wanted.isEmpty())
        return QString();
    std::unique_ptr<GpgME::Context> context(GpgME::Context::createForProtocol(GpgME::OpenPGP));
    if (!context)
        return QString();
    if (context->setPinentryMode(GpgME::Context::PinentryCancel))
        return QString();
    QString found;
    GpgME::Error error = context->startKeyListing("", true);
    while (!error) {
        const GpgME::Key key = context->nextKey(error);
        if (error || key.isNull())
            break;
        if (textOf(key.keyID()).toLower() == wanted)
            found = textOf(key.primaryFingerprint());
        if (found.isEmpty()) {
            for (const GpgME::Subkey &subkey : key.subkeys()) {
                if (textOf(subkey.keyID()).toLower() == wanted)
                    found = textOf(key.primaryFingerprint());
            }
        }
        if (!found.isEmpty())
            break;
    }
    context->endKeyListing();
    return found;
}

QString decryptFingerprint(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return QString();
    if (!file.seek(16))
        return QString();
    const QByteArray payload = file.readAll();
    if (payload.isEmpty() || payload.size() > 32 * 1024 * 1024)
        return QString();
    gpgmeOnce();
    std::unique_ptr<GpgME::Context> context(GpgME::Context::createForProtocol(GpgME::OpenPGP));
    if (!context)
        return QString();
    if (context->setPinentryMode(GpgME::Context::PinentryCancel))
        return QString();
    GpgME::Data encrypted(payload.constData(), size_t(payload.size()), true);
    GpgME::Data plain;
    const GpgME::DecryptionResult result = context->decrypt(encrypted, plain);
    if (result.error())
        return QString();
    const std::vector<GpgME::DecryptionResult::Recipient> recipients = result.recipients();
    for (const auto &recipient : recipients) {
        const QString fingerprint = fingerprintFor(textOf(recipient.keyID()));
        if (validFingerprint(fingerprint))
            return fingerprint;
    }
    return QString();
}

GpgME::Key secretKey(const QString &fingerprint)
{
    gpgmeOnce();
    std::unique_ptr<GpgME::Context> context(GpgME::Context::createForProtocol(GpgME::OpenPGP));
    if (!context || !validFingerprint(fingerprint))
        return GpgME::Key();
    if (context->setPinentryMode(GpgME::Context::PinentryCancel))
        return GpgME::Key();
    GpgME::Error error;
    const GpgME::Key key = context->key(fingerprint.toLatin1().constData(), error, true);
    if (error || key.isNull())
        return GpgME::Key();
    bool canEncrypt = key.canEncrypt();
    for (const GpgME::Subkey &subkey : key.subkeys()) {
        if (subkey.canEncrypt())
            canEncrypt = true;
    }
    if (!canEncrypt)
        return GpgME::Key();
    return key;
}

bool replyOpens(const QDBusMessage &reply)
{
    if (reply.type() != QDBusMessage::ReplyMessage)
        return false;
    const QList<QVariant> arguments = reply.arguments();
    if (arguments.isEmpty())
        return true;
    bool ok = false;
    const int handle = arguments.at(0).toInt(&ok);
    if (!ok)
        return true;
    return handle >= 0;
}

bool tryPam(const QByteArray &hash)
{
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected())
        return false;
    const struct {
        const char *service;
        const char *path;
        const char *interfaceName;
    } targets[] = {
        {"org.kde.ksecretd", "/ksecretd", "org.kde.KWallet"},
        {"org.kde.ksecretd", "/ksecretd", "org.kde.kwalletcompat"},
        {"org.kde.kwalletd6", "/modules/kwalletd6", "org.kde.KWallet"},
        {"org.kde.kwalletd5", "/modules/kwalletd5", "org.kde.KWallet"},
    };
    for (const auto &target : targets) {
        for (int extra = 0; extra < 2; ++extra) {
            QDBusMessage message = QDBusMessage::createMethodCall(
                QString::fromLatin1(target.service),
                QString::fromLatin1(target.path),
                QString::fromLatin1(target.interfaceName),
                QStringLiteral("pamOpen"));
            message << QStringLiteral("kdewallet") << hash;
            if (extra == 1)
                message << int(0);
            const QDBusMessage reply = bus.call(message, QDBus::Block, 1500);
            if (replyOpens(reply))
                return true;
        }
    }
    return false;
}

void dbusMethod(const QString &method, const QVariantList &arguments)
{
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected())
        return;
    const struct {
        const char *service;
        const char *path;
    } targets[] = {
        {"org.kde.ksecretd", "/ksecretd"},
        {"org.kde.kwalletd6", "/modules/kwalletd6"},
        {"org.kde.kwalletd5", "/modules/kwalletd5"},
    };
    for (const auto &target : targets) {
        QDBusMessage message = QDBusMessage::createMethodCall(
            QString::fromLatin1(target.service),
            QString::fromLatin1(target.path),
            QStringLiteral("org.kde.KWallet"),
            method);
        for (const QVariant &argument : arguments)
            message << argument;
        bus.call(message, QDBus::Block, 1500);
    }
}

void dbusOpen()
{
    dbusMethod(QStringLiteral("open"), {QStringLiteral("kdewallet"), qlonglong(0), QStringLiteral("wasd-wallet")});
}

QByteArray passwordHash(const QByteArray &password, const QByteArray &salt)
{
    QByteArray hash(PBKDF2_SHA512_KEYSIZE, 0);
    const int ok = PKCS5_PBKDF2_HMAC(
        password.constData(),
        int(password.size()),
        reinterpret_cast<const unsigned char *>(salt.constData()),
        int(salt.size()),
        PBKDF2_SHA512_ITERATIONS,
        EVP_sha512(),
        PBKDF2_SHA512_KEYSIZE,
        reinterpret_cast<unsigned char *>(hash.data()));
    if (ok != 1) {
        wipe(hash);
        return QByteArray();
    }
    return hash;
}

void bestEffortPam(const WalletPaths &paths, const QByteArray &password)
{
    QFile saltFile(paths.salt);
    if (!saltFile.open(QIODevice::ReadOnly))
        return;
    const QByteArray salt = saltFile.readAll();
    if (salt.size() != PBKDF2_SHA512_SALTSIZE)
        return;
    QByteArray hash = passwordHash(password, salt);
    if (!hash.isEmpty())
        tryPam(hash);
    wipe(hash);
}

int kindCommand()
{
    const WalletPaths paths = walletPaths();
    const int cipher = headerCipher(paths.file);
    if (cipher == kMissing) {
        std::printf("missing\n");
        return 0;
    }
    if (cipher == kUnreadable)
        return 1;
    if (blowfishCipher(cipher)) {
        std::printf("blowfish\n");
        return 0;
    }
    if (cipher == kCipherGpg) {
        const QString fingerprint = decryptFingerprint(paths.file);
        if (validFingerprint(fingerprint))
            std::printf("gpg %s\n", fingerprint.toLatin1().constData());
        else
            std::printf("gpg\n");
        return 0;
    }
    std::printf("other\n");
    return 0;
}

bool addFolders(KWallet::Backend &backend)
{
    backend.createFolder(QStringLiteral("Passwords"));
    backend.createFolder(QStringLiteral("Form Data"));
    return true;
}

int createBlowfish(const QByteArray &password)
{
    const WalletPaths paths = walletPaths();
    const int ready = prepareCreate(paths);
    if (ready != 0)
        return ready;
    KWallet::Backend backend(QStringLiteral("kdewallet"));
    backend.setCipherType(KWallet::BACKEND_CIPHER_BLOWFISH);
    const int opened = backend.open(password);
    if (opened != 0 || !backend.isOpen()) {
        if (backend.isOpen())
            backend.close(false);
        QFile::remove(paths.file);
        std::fprintf(stderr, "The wallet file was not written.\n");
        return 1;
    }
    addFolders(backend);
    if (backend.close(true) != 0 || !blowfishCipher(headerCipher(paths.file))) {
        QFile::remove(paths.file);
        std::fprintf(stderr, "The wallet file was not written.\n");
        return 1;
    }
    bestEffortPam(paths, password);
    return 0;
}

int createGpg(const QString &fingerprint)
{
    const WalletPaths paths = walletPaths();
    const int ready = prepareCreate(paths);
    if (ready != 0)
        return ready;
    const GpgME::Key key = secretKey(fingerprint);
    if (key.isNull()) {
        std::fprintf(stderr, "The wallet key was not found.\n");
        return 1;
    }
    KWallet::Backend backend(QStringLiteral("kdewallet"));
    backend.setCipherType(KWallet::BACKEND_CIPHER_GPG);
    const int opened = backend.open(key);
    if (opened != 0 || !backend.isOpen()) {
        if (backend.isOpen())
            backend.close(false);
        QFile::remove(paths.file);
        std::fprintf(stderr, "The wallet file was not written.\n");
        return 1;
    }
    addFolders(backend);
    if (backend.close(true) != 0 || headerCipher(paths.file) != kCipherGpg) {
        QFile::remove(paths.file);
        std::fprintf(stderr, "The wallet file was not written.\n");
        return 1;
    }
    dbusOpen();
    return 0;
}

int openGpg()
{
    const WalletPaths paths = walletPaths();
    if (headerCipher(paths.file) != kCipherGpg) {
        std::fprintf(stderr, "The wallet could not be opened.\n");
        return 1;
    }
    dbusOpen();
    return 0;
}

int selfCheck()
{
    char name[] = "/tmp/wasd-wallet-file-XXXXXX";
    if (!mkdtemp(name))
        return 1;
    const QByteArray home(name);
    qputenv("HOME", home);
    qputenv("XDG_DATA_HOME", home + "/.local/share");
    qunsetenv("DBUS_SESSION_BUS_ADDRESS");
    qunsetenv("XDG_RUNTIME_DIR");
    int argc = 1;
    char program[] = "wasd-wallet-file";
    char *argv[] = {program, nullptr};
    QCoreApplication app(argc, argv);
    int result = 1;
    const QString root = QString::fromLocal8Bit(home);
    const QString wallet = root + QStringLiteral("/.local/share/kwalletd/kdewallet.kwl");
    if (QFile::exists(wallet)) {
        std::fprintf(stderr, "The wallet self-check refused an existing wallet.\n");
    } else {
        Secret password;
        password.bytes = QByteArray("wasd-wallet-self-check");
        const int created = createBlowfish(password.bytes);
        const WalletPaths paths = walletPaths();
        QFile saltFile(paths.salt);
        const bool saltReady = saltFile.exists() && saltFile.size() == PBKDF2_SHA512_SALTSIZE;
        bool reopened = false;
        if (created == 0 && saltReady && blowfishCipher(headerCipher(paths.file))) {
            KWallet::Backend backend(QStringLiteral("kdewallet"));
            const int opened = backend.open(password.bytes);
            reopened = opened == 0 && backend.isOpen() && backend.cipherType() == KWallet::BACKEND_CIPHER_BLOWFISH;
            if (backend.isOpen())
                backend.close(false);
        }
        wipe(password.bytes);
        if (created == 0 && reopened) {
            std::printf("wallet file self-check ok\n");
            result = 0;
        } else {
            std::fprintf(stderr, "The wallet self-check could not write a wallet.\n");
        }
    }
    QDir(root).removeRecursively();
    return result;
}

void pinHome()
{
    const QByteArray home = qgetenv("HOME");
    if (!home.isEmpty())
        qputenv("XDG_DATA_HOME", home + "/.local/share");
}

} // namespace

int main(int argc, char **argv)
{
    if (argc == 2 && std::strcmp(argv[1], "self-check") == 0)
        return selfCheck();
    pinHome();
    QCoreApplication app(argc, argv);
    if (argc < 2) {
        std::fprintf(stderr, "The wallet was not set up.\n");
        return 2;
    }
    const QString action = QString::fromLocal8Bit(argv[1]);
    if (action == QLatin1String("kind") && argc == 2)
        return kindCommand();
    if (action == QLatin1String("open-gpg") && argc == 2)
        return openGpg();
    if (action == QLatin1String("create-gpg") && argc == 3) {
        const QString fingerprint = QString::fromLocal8Bit(argv[2]);
        if (!validFingerprint(fingerprint)) {
            std::fprintf(stderr, "The wallet key was not found.\n");
            return 1;
        }
        return createGpg(fingerprint);
    }
    // A password install does not call this program. Blowfish stays in the
    // self-check so the image build can prove the wallet library writes a file.
    std::fprintf(stderr, "The wallet was not set up.\n");
    return 2;
}
