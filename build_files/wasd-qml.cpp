// Open one Qt 6 QML file. Bazzite has the Qt libraries and not the qml tool.
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QUrl>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    if (argc < 2)
        return 2;
    QQmlApplicationEngine engine;
    engine.load(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    if (engine.rootObjects().isEmpty())
        return 1;
    return app.exec();
}
