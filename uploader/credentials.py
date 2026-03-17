import os


def get_erp_credentials():
    login_id = os.getenv("ERP_LOGIN_ID")
    login_pw = os.getenv("ERP_LOGIN_PW")
    if not login_id or not login_pw:
        raise RuntimeError(
            "Missing ERP credentials in environment variables (ERP_LOGIN_ID, ERP_LOGIN_PW).\n"
            "- PowerShell (current session): $env:ERP_LOGIN_ID='YOUR_ID'; $env:ERP_LOGIN_PW='YOUR_PW'\n"
            "- Persistent: setx ERP_LOGIN_ID \"YOUR_ID\"; setx ERP_LOGIN_PW \"YOUR_PW\""
        )
    return login_id, login_pw
