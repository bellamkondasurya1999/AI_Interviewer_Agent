$message = @'
Add Firebase auth, storage, and hosting setup.

This integrates Firebase authentication and resume persistence, updates UI branding to Sura, and adds Firebase Hosting configuration while cleaning up unused test/scripts.
'@

git add .
git commit -m $message
git status -sb
