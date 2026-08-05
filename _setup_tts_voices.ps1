$ErrorActionPreference = 'Continue'
# Expose OneCore voices (Huihui/Kangkang/Yaoyao + any Natural neural voices)
# to SAPI5 by copying registry tokens. Requires admin rights for HKLM write;
# silently skips when not elevated.
$log = "$env:TEMP\tts_voice_setup.log"
Remove-Item $log -Force -ErrorAction SilentlyContinue

$src = 'HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens'
$dests = @(
    'HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\SPEECH\Voices\Tokens'
)
$count = 0
if (Test-Path $src) {
    Get-ChildItem $src | ForEach-Object {
        $tokenName = $_.PSChildName
        foreach ($d in $dests) {
            if (-not (Test-Path "$d\$tokenName")) {
                try {
                    Copy-Item $_.PSPath "$d\$tokenName" -Recurse -ErrorAction Stop
                    $count++
                    Add-Content -Path $log -Value "Copied: $tokenName"
                } catch {
                    Add-Content -Path $log -Value "FAILED: $tokenName : $_"
                }
            }
        }
    }
}
Add-Content -Path $log -Value "Exposed $count OneCore tokens to SAPI5"
