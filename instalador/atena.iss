; Instalador da ATENA (Inno Setup). Gerado automaticamente pelo GitHub Actions.
#define Versao GetEnv("ATENA_VERSAO")
#if Versao == ""
  #define Versao "0.5.0"
#endif

[Setup]
AppId={{6F2C1B7E-3A41-4C8E-9D3B-A7E5ATENA0001}
AppName=ATENA
AppVersion={#Versao}
AppVerName=ATENA {#Versao}
AppPublisher=Guilherme
AppComments=Assistente Tecnológica de Execução e Navegação Artificial
DefaultDirName={localappdata}\Programs\ATENA
DefaultGroupName=ATENA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ATENA-Setup
SetupIconFile=..\assets\atena.ico
UninstallDisplayIcon={app}\ATENA.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na Área de Trabalho"
Name: "iniciar"; Description: "Abrir a ATENA junto com o Windows (pra palmas e ""Atena"" funcionarem sempre)"
Name: "ollama"; Description: "Instalar o Ollama, o cérebro da ATENA (recomendado se ainda não tiver)"
Name: "lhm"; Description: "Instalar o LibreHardwareMonitor (temperaturas e clocks no monitor do PC)"; Flags: unchecked

[Files]
Source: "..\dist\ATENA\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\ATENA"; Filename: "{app}\ATENA.exe"
Name: "{group}\Desinstalar a ATENA"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ATENA"; Filename: "{app}\ATENA.exe"; Tasks: atalho
Name: "{userstartup}\ATENA"; Filename: "{app}\ATENA.exe"; Tasks: iniciar

[Run]
Filename: "{cmd}"; Parameters: "/c winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements"; StatusMsg: "Instalando o Ollama (pode demorar alguns minutos)..."; Tasks: ollama; Flags: runhidden waituntilterminated
Filename: "{cmd}"; Parameters: "/c winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor --accept-package-agreements --accept-source-agreements"; StatusMsg: "Instalando o LibreHardwareMonitor..."; Tasks: lhm; Flags: runhidden waituntilterminated
Filename: "{app}\ATENA.exe"; Description: "Abrir a ATENA agora"; Flags: nowait postinstall skipifsilent
