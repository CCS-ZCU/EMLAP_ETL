# to communicate with google spreadsheet...
import json
import gspread
from gspread_dataframe import get_as_dataframe
from gspread_dataframe import set_with_dataframe
from google.oauth2 import service_account # based on google-auth library

# establish connection with gogglesheets...
def setup(sheet_url=None, service_account_path=None):
    if service_account_path==None:
        service_account_path = input("insert path to your ServiceAccountKey.json file: ")
    file_data = json.load(open(service_account_path, "r"))
    credentials = service_account.Credentials.from_service_account_info(file_data)
    gc = gspread.Client(auth=credentials.with_scopes(['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']))
    if sheet_url == None:
        sheet_url = input("insert url of the spreadsheet you want to connect to: ")
    sheet = gc.open_by_url(sheet_url)
    return sheet