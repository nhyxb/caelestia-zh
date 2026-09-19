import QtQuick
import Caelestia.I18n
import qs.components

Item {
    id: root

    property int count: 0
    property bool enabled: false

    StyledText {
        text: root.enabled ? Tr.trCtx("Enabled", "toggle label") : Tr.trCtx("Enabled", "panel status")
    }

    StyledText {
        text: Tr.trCtx("Disabled", "panel status")
    }

    StyledText {
        text: Tr.trN("%n device available", "%n devices available", root.count)
    }

    StyledText {
        text: Tr.tr("Connect")
    }

    StyledText {
        text: Tr.tr("Connection")
    }

    StyledText {
        text: Tr.tr("Paused")
    }

    StyledText {
        text: Tr.trCtx("PAUSED", "recording status")
    }

    StyledText {
        text: Tr.trCtx("Open", "wifi security type")
    }

    StyledText {
        text: Tr.tr("Open settings")
    }
}
