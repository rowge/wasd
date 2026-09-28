var allPanels = panels();
for (var i = 0; i < allPanels.length; i++) {
    var widgets = allPanels[i].widgets();
    for (var j = 0; j < widgets.length; j++) {
        var widget = widgets[j];
        if (widget.type === "org.kde.plasma.kickoff" || widget.type === "org.kde.plasma.kicker") {
            widget.currentConfigGroup = ["General"];
            widget.writeConfig("icon", "wasd-logo");
            widget.reloadConfig();
        }
    }
}
