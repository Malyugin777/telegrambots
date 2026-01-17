$ErrorActionPreference = "Continue"

$SERVER = "66.151.33.167"
$USER = "root"
$PASSWORD = "mcMdC3d+2b"

Write-Host "=== Nexus VPS Deployment ===" -ForegroundColor Cyan

# Check and install Posh-SSH
if (-not (Get-Module -ListAvailable -Name Posh-SSH)) {
    Write-Host "Installing Posh-SSH..." -ForegroundColor Yellow
    Install-Module -Name Posh-SSH -Force -Scope CurrentUser -AllowClobber
}
Import-Module Posh-SSH -ErrorAction SilentlyContinue

$SecurePassword = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$Credential = New-Object System.Management.Automation.PSCredential($USER, $SecurePassword)

Write-Host "Connecting to $SERVER..." -ForegroundColor Yellow

$Session = New-SSHSession -ComputerName $SERVER -Credential $Credential -AcceptKey -Force -ErrorAction Stop

if ($Session.Connected) {
    Write-Host "Connected!" -ForegroundColor Green

    $commands = @(
        "apt-get update && apt-get install -y git docker.io docker-compose",
        "systemctl start docker && systemctl enable docker",
        "rm -rf /root/nexus_project",
        "git clone https://github.com/Malyugin777/telegrambots.git /root/nexus_project",
        "cd /root/nexus_project/infrastructure && cp .env.example .env",
        "cd /root/nexus_project/infrastructure && docker-compose up -d --build"
    )

    foreach ($cmd in $commands) {
        Write-Host "> $cmd" -ForegroundColor Cyan
        $result = Invoke-SSHCommand -SessionId $Session.SessionId -Command $cmd -TimeOut 600
        if ($result.Output) { Write-Host $result.Output }
        if ($result.Error) { Write-Host $result.Error -ForegroundColor Red }
    }

    Remove-SSHSession -SessionId $Session.SessionId
    Write-Host "=== Done ===" -ForegroundColor Green
} else {
    Write-Host "Failed to connect!" -ForegroundColor Red
}
