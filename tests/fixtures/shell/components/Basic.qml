import QtQuick
import Caelestia.I18n
import qs.components

Item {
    id: root

    property string iconName: "palette"

    StyledText {
        text: Tr.tr("Wallpaper & style")
    }

    StyledText {
        text: Tr.tr("Cancel")
    }

    StyledText {
        text: Tr.tr("Notifications")
    }

    MaterialIcon {
        text: "chevron_right"
    }

    // Tr.tr("Commented out string")
    // description: Tr.tr("Also commented out")
    // text: Tr.tr("Cancel")

    /* Tr.tr("Block comment string") */

    StyledText {
        text: Tr.tr(root.iconName)
    }

    StyledText {
        text: Tr.tr('Single quoted')
    }

    StyledText {
        text: Tr.tr(`Backtick quoted`)
    }

    StyledText {
        text: Tr.tr("Quotes \"inside\" here")
    }

    StyledText {
        text: Tr.tr("Line one\nLine two")
    }

    StyledText {
        text: Tr.tr("%1 B/s").arg(value)
    }

    action: Action {
        text: Tr.tr(
            "All up to date!"
        )
    }
}
