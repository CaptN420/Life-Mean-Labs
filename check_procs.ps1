Get-CimInstance Win32_Process |
Where-Object {
    $_.Name -match 'python|node|ollama|docker|comfy|swarm'
} |
Select-Object ProcessId,Name,CommandLine |
Format-List
