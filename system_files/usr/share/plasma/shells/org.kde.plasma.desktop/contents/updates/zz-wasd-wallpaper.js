var image = "file:///usr/share/wallpapers/wasd/stained-glass.jpg";
try {
    var choice = ConfigFile("wasd-wallpaperrc");
    choice.group = "Wallpaper";
    var picked = String(choice.readEntry("Image"));
    var prefix = "file:///usr/share/wallpapers/wasd/";
    var rest = picked.slice(prefix.length);
    if (picked.indexOf(prefix) === 0 && rest.length > 0 && rest.indexOf("/") < 0 && rest.indexOf("..") < 0) {
        image = picked;
    }
} catch (e) {
}

// Plasma 6.8 leaves a desktop's activity id blank after an update. The old
// desktop list is empty then, and a script that walks it changes nothing.
// desktopForScreen still finds the desktop on each screen.
for (var i = 0; i < screenCount; i++) {
    var desktop = desktopForScreen(i);
    if (!desktop) {
        continue;
    }
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig("Image", image);
    desktop.reloadConfig();
}
