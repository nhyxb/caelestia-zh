import QtQuick
import Caelestia.I18n

QtObject {
    id: root

    function show(title, message) {
        Toast.show(Tr.markCtx(title, "toast", [Tr.tr("Notifications")]));
        Toast.show(Tr.trMarked(message));
        Toast.show(Tr.mark("Recording for %1", [seconds]));
    }

    property string dynamicText: Tr.tr(someVariable)

    property bool ready: Tr.trCtx("Ready", "recorder state") !== undefined
}
