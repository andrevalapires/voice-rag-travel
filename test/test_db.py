import os
import pyodbc
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Retrieves the duration of a flight between two locations
def get_flight_duration(source: str, destination: str, conn) -> float:
    # SQL query to select the flight duration
    query = """
    SELECT Duration
    FROM dbo.FlightDuration
    WHERE Source = ? AND Destination = ?
    """
    # Execute the query
    cursor = conn.cursor()
    cursor.execute(query, (source, destination))

    # Fetch the result
    row = cursor.fetchone()

    # Check if we got a result
    if row:
        return row.Duration # Return the duration value from the result
    else:
        return 0.0  # Return 0.0 or an appropriate value if no data is found

# Retrieves the price of a flight between two locations
def get_flight_price(source: str, destination: str, trip_date: str, conn) -> float:
    # SQL query to select the flight price
    query = """
    SELECT Price
    FROM dbo.FlightPrice
    WHERE Source = ? AND Destination = ? AND StartDate <= ? AND EndDate >= ?
    """
    # Execute the query
    cursor = conn.cursor()
    cursor.execute(query, (source, destination, trip_date, trip_date))
    
    # Fetch the result
    row = cursor.fetchone()
    
    # Check if we got a result
    if row:
        return float(row.Price)  # Return the price value from the result
    else:
        return 0.0  # Return 0.0 or an appropriate value if no data is found

if __name__ == "__main__":    
    load_dotenv()
    db_server = os.environ.get("AZURE_SQL_SERVER")
    db_name = os.environ.get("AZURE_SQL_DATABASE")
    db_user = os.environ.get("AZURE_SQL_USER")
    db_password = os.environ.get("AZURE_SQL_PASSWORD")

    # Use DefaultAzureCredential for Azure AD authentication
    #credential = DefaultAzureCredential()
    #token = credential.get_token("https://database.windows.net/.default")

    #db_connection_string = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={db_server};DATABASE={db_name};Authentication=ActiveDirectoryInteractive;'

    db_connection_string = f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{db_server},1433;Database={db_name};Uid={db_user};Pwd={db_password};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'

    # Open a connection to the database
    conn = pyodbc.connect(db_connection_string)

    current_location = "LIS"
    destination = "ORD"
    trip_date = "2024-08-01"

    duration = get_flight_duration(current_location, destination, conn)
    price = get_flight_price(current_location, destination, trip_date, conn)

    result = {
        "source": current_location,
        "destination": destination,
        "price": price,
        "duration": duration,
        "trip_date": trip_date
    }

    # close the database connection
    conn.close()

    print(result)