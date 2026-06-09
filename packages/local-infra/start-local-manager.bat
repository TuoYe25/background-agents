@echo off
echo Starting Local Sandbox Manager...
echo.

set LOCAL_SANDBOX_API_KEY=local-dev-key
set LOCAL_SANDBOX_MAX_CONCURRENT=1
set LOCAL_SANDBOX_DEV_MODE=true

python -m local_sandbox_manager.main

pause