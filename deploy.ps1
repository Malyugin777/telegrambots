# Nexus Project Deploy Script
# Run: powershell -ExecutionPolicy Bypass -File deploy.ps1

$SERVER = "66.151.33.167"
$USER = "root"
$PASSWORD = "mcMdC3d+2b"
$REMOTE_PATH = "/root/nexus_project"
$LOCAL_PATH = $PSScriptRoot

Write-Host "=== Nexus Project Deployment ===" -ForegroundColor Cyan

# Install Posh-SSH if not present
if (-not (Get-Module -ListAvailable -Name Posh-SSH)) {
    Write-Host "Installing Posh-SSH module..." -ForegroundColor Yellow
    Install-Module -Name Posh-SSH -Force -Scope CurrentUser
}

Import-Module Posh-SSH

# Create credential
$SecurePassword = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$Credential = New-Object System.Management.Automation.PSCredential($USER, $SecurePassword)

Write-Host "Connecting to $SERVER..." -ForegroundColor Yellow

try {
    # Create SSH session
    $Session = New-SSHSession -ComputerName $SERVER -Credential $Credential -AcceptKey -Force

    if ($Session) {
        Write-Host "Connected!" -ForegroundColor Green

        # Create directory
        Write-Host "Creating remote directory..." -ForegroundColor Yellow
        Invoke-SSHCommand -SessionId $Session.SessionId -Command "mkdir -p $REMOTE_PATH"

        # Create SFTP session for file transfer
        Write-Host "Starting file transfer..." -ForegroundColor Yellow
        $SFTPSession = New-SFTPSession -ComputerName $SERVER -Credential $Credential -AcceptKey -Force

        # Upload folders
        $folders = @("infrastructure", "bot_net", "admin_panel", "shared")
        foreach ($folder in $folders) {
            $localFolder = Join-Path $LOCAL_PATH $folder
            if (Test-Path $localFolder) {
                Write-Host "Uploading $folder..." -ForegroundColor Cyan
                Set-SFTPItem -SessionId $SFTPSession.SessionId -Path $localFolder -Destination $REMOTE_PATH -Force
            }
        }

        # Upload root files
        $files = @("README.md", "PROJECT_DESCRIPTION.md", "DOMAIN_SETUP_GUIDE.md", ".gitignore")
        foreach ($file in $files) {
            $localFile = Join-Path $LOCAL_PATH $file
            if (Test-Path $localFile) {
                Write-Host "Uploading $file..." -ForegroundColor Cyan
                Set-SFTPItem -SessionId $SFTPSession.SessionId -Path $localFile -Destination $REMOTE_PATH -Force
            }
        }

        Write-Host "Files uploaded!" -ForegroundColor Green

        # Run docker-compose
        Write-Host "Running docker-compose..." -ForegroundColor Yellow
        $result = Invoke-SSHCommand -SessionId $Session.SessionId -Command "cd $REMOTE_PATH/infrastructure && docker-compose up -d --build"
        Write-Host $result.Output

        # Cleanup
        Remove-SSHSession -SessionId $Session.SessionId
        Remove-SFTPSession -SessionId $SFTPSession.SessionId

        Write-Host "=== Deployment Complete ===" -ForegroundColor Green
    }
}
catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
