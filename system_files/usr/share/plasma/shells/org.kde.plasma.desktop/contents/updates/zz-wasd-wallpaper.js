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

var allDesktops = desktops();
for (var i = 0; i < allDesktops.length; i++) {
    var desktop = allDesktops[i];
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig("Image", image);
}
