# Pushes this folder's code to github.com/US_Versus/Advocates
# Right-click this file -> "Run with PowerShell" (or paste into a PowerShell window)
# Safe: the .gitignore in this folder blocks every data file (db/csv/xlsx/docx/pptx).

cd "C:\Users\RMand\Desktop\Claude Supernus\Database\crm_app"

git init -b main
git add .

Write-Host ""
Write-Host "Files about to be uploaded (should be ~10 code/doc files, NO .db or member data):" -ForegroundColor Yellow
git status --short
Write-Host ""
pause   # press Enter if the list looks right; close the window if you see any data file

git commit -m "Advocacy CRM - served queue, approved discussion guides, cadence engine"
git remote add origin https://github.com/US_Versus/Advocates.git
git push -u origin main

Write-Host ""
Write-Host "Done. Check https://github.com/US_Versus/Advocates in your browser." -ForegroundColor Green
pause
