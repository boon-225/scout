import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.qfield.core
import org.qfield.gui

/**
 * \ingroup qml_app
 *
 * White-label About page (replaces QField's QfAbout.qml at build time; see branding/apply.py).
 * Shows the client's logo, organisation, support and help links, and a neutral open-source notice.
 * Values in @...@ are filled in from customers/<key>/customer.yml.
 */
Item {
  id: aboutPanel

  visible: false
  focus: visible

  readonly property string organisation: "@ORGANISATION@"
  readonly property string website: "@WEBSITE@"
  readonly property string supportEmail: "@SUPPORT_EMAIL@"
  readonly property string helpUrl: "@HELP_URL@"
  readonly property string privacyUrl: "@PRIVACY_URL@"
  readonly property string sourceUrl: "@SOURCE_URL@"

  Rectangle {
    color: "black"
    opacity: 0.8
    anchors.fill: parent
  }

  ColumnLayout {
    id: aboutContainer
    spacing: 6
    anchors.fill: parent
    anchors.margins: 20
    anchors.topMargin: 20 + mainWindow.sceneTopMargin
    anchors.bottomMargin: 20 + mainWindow.sceneBottomMargin

    ScrollView {
      Layout.fillWidth: true
      Layout.fillHeight: true
      ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
      ScrollBar.vertical: QfScrollBar {}
      contentItem: information
      contentWidth: information.width
      contentHeight: information.height
      clip: true

      MouseArea {
        anchors.fill: parent
        onClicked: aboutPanel.visible = false
      }

      ColumnLayout {
        id: information
        spacing: 12
        width: aboutPanel.width - 40
        height: Math.max(mainWindow.height - helpButton.height - appDirectoryLabel.height - aboutContainer.spacing * 3 - aboutContainer.anchors.topMargin - aboutContainer.anchors.bottomMargin - 10, appPart.height)

        ColumnLayout {
          id: appPart
          Layout.fillWidth: true
          Layout.fillHeight: true
          spacing: 10

          Image {
            id: appLogo
            Layout.preferredWidth: 138
            Layout.preferredHeight: 138
            Layout.alignment: Qt.AlignHCenter
            fillMode: Image.PreserveAspectFit
            source: "qrc:/images/app_logo.svg"
            sourceSize.width: width * screen.devicePixelRatio
            sourceSize.height: height * screen.devicePixelRatio
          }

          Label {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignCenter
            horizontalAlignment: Text.AlignHCenter
            font: QfTheme.strongFont
            color: QfTheme.light
            textFormat: Text.RichText
            wrapMode: Text.WordWrap
            text: {
              const dependencies = [["QGIS", Qfield.qgisVersion.split("-", 1)[0]], ["GDAL/OGR", Qfield.gdalVersion], ["Qt", Qfield.qtVersion]];
              return Qfield.name + "<br>" + Qfield.versionString + "<br><small>" + dependencies.map(pair => pair.join(" ")).join(" | ") + "</small>";
            }
          }

          Label {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignCenter
            horizontalAlignment: Text.AlignHCenter
            font: QfTheme.defaultFont
            color: QfTheme.light
            textFormat: Text.RichText
            wrapMode: Text.WordWrap
            text: {
              let lines = [aboutPanel.organisation];
              if (aboutPanel.website !== "")
                lines.push('<a href="' + aboutPanel.website + '">' + aboutPanel.website.replace(/^https?:\/\//, '') + '</a>');
              if (aboutPanel.supportEmail !== "")
                lines.push(qsTr("Support:") + ' <a href="mailto:' + aboutPanel.supportEmail + '">' + aboutPanel.supportEmail + '</a>');
              if (aboutPanel.privacyUrl !== "")
                lines.push('<a href="' + aboutPanel.privacyUrl + '">' + qsTr("Privacy policy") + '</a>');
              return lines.join("<br>");
            }
            onLinkActivated: link => Qt.openUrlExternally(link)
          }

          Label {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignCenter
            Layout.topMargin: 10
            horizontalAlignment: Text.AlignHCenter
            font: QfTheme.tinyFont
            color: QfTheme.secondaryTextColor
            textFormat: Text.RichText
            wrapMode: Text.WordWrap
            text: {
              let notice = qsTr("This app is free software, built from open-source components and licensed under the GNU General Public License.");
              if (aboutPanel.sourceUrl !== "") {
                notice += ' <a href="' + aboutPanel.sourceUrl + '">' + qsTr("Source code and licences") + '</a>';
              } else if (aboutPanel.supportEmail !== "") {
                notice += ' ' + qsTr("The source code is available on request from %1.").arg('<a href="mailto:' + aboutPanel.supportEmail + '">' + aboutPanel.supportEmail + '</a>');
              }
              return notice;
            }
            onLinkActivated: link => Qt.openUrlExternally(link)
          }
        }
      }
    }

    Label {
      id: appDirectoryLabel
      Layout.fillWidth: true
      Layout.maximumWidth: parent.width
      Layout.alignment: Qt.AlignCenter
      Layout.bottomMargin: 10
      horizontalAlignment: Text.AlignHCenter
      font: QfTheme.tinyFont
      color: QfTheme.secondaryTextColor
      textFormat: Text.RichText
      wrapMode: Text.WordWrap

      text: {
        let label = '';
        let isDesktopPlatform = Qt.platform.os !== "ios" && Qt.platform.os !== "android";
        let dataDirs = platformUtilities.appDataDirs();
        if (dataDirs.length > 0) {
          label = dataDirs.length > 1 ? qsTr('%1 app directories').arg(Qfield.name) : qsTr('%1 app directory').arg(Qfield.name);
          for (let dataDir of dataDirs) {
            if (isDesktopPlatform) {
              label += '<br><a href="' + QfUrlUtils.fromString(dataDir) + '">' + dataDir + '</a>';
            } else {
              label += '<br>' + dataDir;
            }
          }
        }
        return label;
      }

      onLinkActivated: link => Qt.openUrlExternally(link)
    }

    QfButton {
      id: helpButton
      Layout.fillWidth: true
      icon.source: QfTheme.getThemeVectorIcon('ic_book_white_24dp')
      visible: aboutPanel.helpUrl !== ""
      text: qsTr('Help')
      onClicked: Qt.openUrlExternally(aboutPanel.helpUrl)
    }
  }

  Keys.onReleased: event => {
    if (event.key === Qt.Key_Back || event.key === Qt.Key_Escape) {
      event.accepted = true;
      visible = false;
    }
  }
}
