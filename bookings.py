#!python3
import os, sys
import cgi
import datetime
import sqlite3
from wsgiref.util import setup_testing_defaults, shift_path_info
from wsgiref.simple_server import make_server

#
# Ensure we're using the same database filename throughout.
# It doesn't matter what this is called or where it is:
# sqlite3 will just accept anything.
#
DATABASE_FILEPATH = "bookings.db"

def create_database():
    """Connect to the database, read the CREATE statements and split
    them at the semicolon into individual statements. Once each
    statement has been executed, close the connection.
    """
    #
    # Since we might be re-running this, delete the file and rebuild
    # it if necessary.
    #
    if os.path.exists(DATABASE_FILEPATH):
        os.remove(DATABASE_FILEPATH)

    #
    # A database cursor the the Python mechanism for running something
    # against any database. You create a cursor and then .execute
    # SQL statements through it.
    #
    db = sqlite3.connect(DATABASE_FILEPATH)
    q = db.cursor()

    #
    # Read all the contents of create.sql in one gulp
    #
    sql = open("create.sql").read()
    #
    # Split it into individual statements, breaking on the semicolon
    #
    statements = sql.split(";")
    #
    # Execute each of the individual statements against the database
    #
    for statement in statements:
        q.execute(statement)

    #
    # Close everything
    #
    q.close()
    db.commit()
    db.close()

def populate_database():
    """Populate the database with some valid test data
    """
    db = sqlite3.connect(DATABASE_FILEPATH)
    q = db.cursor()

    sql = "INSERT INTO users(id, name, email_address) VALUES(?, ?, ?)"
    q.execute(sql, [1, "Mickey Mouse", "mickey.mouse@example.com"])
    q.execute(sql, [2, "Donald Duck", "donald.duck@example.com"])
    q.execute(sql, [3, "Kermit the Frog", None])

    sql = "INSERT INTO drones(id, name, location) VALUES(?, ?, ?)"
    q.execute(sql, [1, "Drone A", "South Street Seaport"])
    q.execute(sql, [2, "Drone B", "Hudson Yards"])
    q.execute(sql, [3, "Drone C", "UN Building"])

    #
    # Triple-quoted strings can cross lines
    # NB the column order doesn't matter if you specify it
    #
    sql = """
    INSERT INTO
        bookings
    (
        drone_id, user_id, booked_on, booked_from, booked_to
    )
    VALUES(
        ?, ?, ?, ?, ?
    )"""
    q.execute(sql, [1, 1, '2014-09-25', '09:00', '10:00']) # drone A (1) booked by Mickey (1) from 9am to 10am on 25th Sep 2014
    q.execute(sql, [3, 1, '2015-09-25', None, None]) # Main Hall (3) booked by Mickey (1) from all day on 25th Sep 2014
    q.execute(sql, [2, 3, '2014-09-22', '12:00', None]) # drone B (2) booked by Kermit (3) from midday onwards on 22nd Sep 2014
    q.execute(sql, [1, 2, '2015-02-14', '09:30', '10:00']) # drone A (1) booked by Donald (2) from 9.30am to 10am on 15th Feb 2014

    q.close()
    db.commit()
    db.close()

def select(sql_statement, params=None):
    """General-purpose routine to read from the database
    """
    if params is None:
        params = []
    db = sqlite3.connect(DATABASE_FILEPATH)
    db.row_factory = sqlite3.Row
    q = db.cursor()
    try:
        q.execute(sql_statement, params)
        return q.fetchall()
    finally:
        q.close()
        db.close()

def execute(sql_statement, params=None):
    """General-purpose routine to write to the database
    """
    if params is None:
        params = []
    db = sqlite3.connect(DATABASE_FILEPATH)
    q = db.cursor()
    try:
        q.execute(sql_statement, params)
        db.commit()
    finally:
        q.close()
        db.close()

def get_user(user_id):
    """Return the user matching user_id
    """
    for user in select("SELECT * FROM users WHERE id = ?", [user_id]):
        return user

def get_drone(drone_id):
    """Return the drone matching drone_id
    """
    for drone in select("SELECT * FROM drones WHERE id = ?", [drone_id]):
        return drone

def get_users():
    """Get all the users from the database
    """
    return select("SELECT * FROM users")

def get_drones():
    """Get all the drones from the database
    """
    return select("SELECT * FROM drones")

def get_bookings():
    """Get all the bookings ever made
    """
    return select("SELECT * FROM v_bookings")

def get_bookings_for_user(user_id):
    """Get all the bookings made by a user
    """
    return select("SELECT * FROM v_bookings WHERE user_id = ?", [user_id])

def get_bookings_for_drone(drone_id):
    """Get all the bookings made against a drone
    """
    return select("SELECT * FROM v_bookings WHERE drone_id = ?", [drone_id])

def add_user_to_database(name, email_address):
    """Add a user to the database
    """
    print("%r, %r" % (name, email_address))
    execute(
        "INSERT INTO users(name, email_address) VALUES (?, ?)",
        [name, email_address]
    )

def add_drone_to_database(name, location):
    """Add a user to the database
    """
    execute(
        "INSERT INTO drones(name, location) VALUES (?, ?)",
        [name, location]
    )

def has_overlapping_bookings(drone_id, booked_on, booked_from=None, booked_to=None):
    """Check if there are any overlapping bookings for the given drone and time period.
    
    Args:
        drone_id: ID of the drone to check
        booked_on: Date of the booking
        booked_from: Start time (optional, defaults to '00:00')
        booked_to: End time (optional, defaults to '23:59')
        
    Returns:
        bool: True if there are overlapping bookings, False otherwise
    """
    # Convert None times to start/end of day
    booked_from = booked_from or '00:00'
    booked_to = booked_to or '23:59'
    
    # Query to find overlapping bookings
    sql = """
    SELECT COUNT(*) FROM bookings 
    WHERE drone_id = ? 
    AND booked_on = ?
    AND (
        (? BETWEEN COALESCE(booked_from, '00:00') AND COALESCE(booked_to, '23:59')
        OR ? BETWEEN COALESCE(booked_from, '00:00') AND COALESCE(booked_to, '23:59'))
        OR
        (COALESCE(booked_from, '00:00') BETWEEN ? AND ?
        OR COALESCE(booked_to, '23:59') BETWEEN ? AND ?)
    )
    """
    params = [drone_id, booked_on, booked_from, booked_to, booked_from, booked_to, booked_from, booked_to]
    
    db = sqlite3.connect(DATABASE_FILEPATH)
    q = db.cursor()
    try:
        q.execute(sql, params)
        count = q.fetchone()[0]
        return count > 0
    finally:
        q.close()
        db.close()

def add_booking_to_database(user_id, drone_id, booked_on, booked_from=None, booked_to=None):
    """Add a booking to the database if there are no overlapping bookings.
    
    Raises:
        ValueError: If there is an overlapping booking for the same drone
    """
    if has_overlapping_bookings(drone_id, booked_on, booked_from, booked_to):
        raise ValueError("Cannot book drone: There is an overlapping booking for this time period")
        
    execute(
        """
        INSERT INTO bookings(user_id, drone_id, booked_on, booked_from, booked_to)
        VALUES(?, ?, ?, ?, ?)
        """,
        [user_id, drone_id, booked_on, booked_from, booked_to]
    )

def page(title, content):
    """Return a complete HTML page with the title as the <title> and <h1>
    tags, and the content within the body, after the <h1>
    """
    return """
    <html>
    <head>
    <title>Drone Booking System: {title}</title>
    <style>
    body {{
        background-colour : #cff;
        margin : 1em;
        padding : 1em;
        border : thin solid black;
        font-family : sans-serif;
    }}
    td {{
        padding : 0.5em;
        margin : 0.5em;
        border : thin solid blue;
    }}

    </style>
    </head>
    <body>
    <h1>{title}</h1>
    {content}
    </body>
    </html>
    """.format(title=title, content=content)

def index_page(environ):
    """Provide a list of all the pages
    """
    html = """
    <ul>
        <li><a href="/users">Users</a></li>
        <li><a href="/drones">Drones</a></li>
        <li><a href="/bookings">Bookings</a></li>
    </ul>
    """
    return page("Starting Page", html)

def users_page(environ):
    """Provide a list of all the users, linking to their bookings
    """
    html = "<ul>"
    for user in get_users():
        html += '<li><a href="/bookings/user/{id}">{name}</a> ({email_address})</li>\n'.format(
            id=user['id'],
            name=user['name'],
            email_address=user['email_address'] or "No email"
        )
    html += "</ul>"
    html += "<hr/>"
    html += """<form method="POST" action="/add-user">
    <label for="name">Name:</label>&nbsp;<input type="text" name="name"/>
    <label for="email_address">Email:</label>&nbsp;<input type="text" name="email_address"/>
    <input type="submit" name="submit" value="Add User"/>
    </form>"""
    return page("Users", html)

def drones_page(environ):
    """Provide a list of all the drones, linking to their bookings
    """
    html = "<ul>"
    for drone in get_drones():
        html += '<li><a href="/bookings/drone/{id}">{name}</a> ({location})</li>\n'.format(
            id=drone['id'],
            name=drone['name'],
            location=drone['location'] or "Location unknown"
        )
    html += "</ul>"
    html += "<hr/>"
    html += """<form method="POST" action="/add-drone">
    <label for="name">Name:</label>&nbsp;<input type="text" name="name"/>
    <label for="location">Location:</label>&nbsp;<input type="text" name="location"/>
    <input type="submit" name="submit" value="Add drone"/>
    </form>"""
    return page("drones", html)

def all_bookings_page(environ, error_message=None):
    """Provide a list of all bookings
    """
    html = "<table>"
    html += "<tr><td>Drone</td><td>User</td><td>Date</td><td>Times</td></tr>"
    for booking in get_bookings():
        html += "<tr><td>{user_name}</td><td>{drone_name}</td><td>{booked_on}</td><td>{booked_from} - {booked_to}</td></tr>".format(
            user_name=booking['user_name'],
            drone_name=booking['drone_name'],
            booked_on=booking['booked_on'],
            booked_from=booking['booked_from'] or "",
            booked_to=booking['booked_to'] or ""
        )
    html += "</table>"

    html += "<hr/>"
    if error_message:
        html += '<div style="color: red; margin-bottom: 1em;">{}</div>'.format(error_message)
    html += '<form method="POST" action="/add-booking">'

    html += '<label for="user_id">User:</label>&nbsp;<select name="user_id">'
    for user in get_users():
        html += '<option value="{id}">{name}</option>'.format(**user)
    html += '</select>'

    html += '&nbsp;|&nbsp;'

    html += '<label for="drone_id">Drone:</label>&nbsp;<select name="drone_id">'
    for drone in get_drones():
        html += '<option value="{id}">{name}</option>'.format(**drone)
    html += '</select>'

    html += '&nbsp;|&nbsp;'
    html += '<label for="booked_on">On</label>&nbsp;<input type="text" name="booked_on" value="{today}"/>'.format(today=datetime.date.today())
    html += '&nbsp;<label for="booked_from">between</label>&nbsp;<input type="text" name="booked_from" />'
    html += '&nbsp;<label for="booked_to">and</label>&nbsp;<input type="text" name="booked_to" />'
    html += '<input type="submit" name="submit" value="Add Booking"/></form>'

    return page("All Bookings", html)


def bookings_user_page(environ, error_message=None):
    """Provide a list of bookings by user, showing drone and date/time
    """
    user_id = int(shift_path_info(environ))
    user = get_user(user_id)
    html = "<table>"
    html += "<tr><td>drone</td><td>Date</td><td>Times</td></tr>"
    for booking in get_bookings_for_user(user_id):
        html += "<tr><td>{drone_name}</td><td>{booked_on}</td><td>{booked_from} - {booked_to}</td></tr>".format(
            drone_name=booking['drone_name'],
            booked_on=booking['booked_on'],
            booked_from=booking['booked_from'] or "",
            booked_to=booking['booked_to'] or ""
        )
    html += "</table>"
    html += "<hr/>"
    if error_message:
        html += '<div style="color: red; margin-bottom: 1em;">{}</div>'.format(error_message)
    html += '<form method="POST" action="/add-booking">'
    html += '<input type="hidden" name="user_id" value="{user_id}"/>'.format(user_id=user_id)
    html += '<label for="drone_id">drone:</label>&nbsp;<select name="drone_id">'
    for drone in get_drones():
        html += '<option value="{id}">{name}</option>'.format(**drone)
    html += '</select>'
    html += '&nbsp;|&nbsp;'
    html += '<label for="booked_on">On</label>&nbsp;<input type="text" name="booked_on" value="{today}"/>'.format(today=datetime.date.today())
    html += '&nbsp;<label for="booked_from">between</label>&nbsp;<input type="text" name="booked_from" />'
    html += '&nbsp;<label for="booked_to">and</label>&nbsp;<input type="text" name="booked_to" />'
    html += '<input type="submit" name="submit" value="Add Booking"/></form>'
    return page("Bookings for %s" % user['name'], html)

def bookings_drone_page(environ, error_message=None):
    """Provide a list of bookings by drone, showing user and date/time
    """
    drone_id = int(shift_path_info(environ))
    drone = get_drone(drone_id)
    html = "<table>"
    html += "<tr><td>User</td><td>Date</td><td>Times</td></tr>"
    for booking in get_bookings_for_drone(drone_id):
        html += "<tr><td>{user_name}</td><td>{booked_on}</td><td>{booked_from} - {booked_to}</td></tr>".format(
            user_name=booking['user_name'],
            booked_on=booking['booked_on'],
            booked_from=booking['booked_from'] or "",
            booked_to=booking['booked_to'] or ""
        )
    html += "</table>"
    html += "<hr/>"
    if error_message:
        html += '<div style="color: red; margin-bottom: 1em;">{}</div>'.format(error_message)
    html += '<form method="POST" action="/add-booking">'
    html += '<input type="hidden" name="drone_id" value="{drone_id}"/>'.format(drone_id=drone_id)
    html += '<label for="user_id">User:</label>&nbsp;<select name="user_id">'
    for user in get_users():
        html += '<option value="{id}">{name}</option>'.format(**user)
    html += '</select>'
    html += '&nbsp;|&nbsp;'
    html += '<label for="booked_on">On</label>&nbsp;<input type="text" name="booked_on" value="{today}"/>'.format(today=datetime.date.today())
    html += '&nbsp;<label for="booked_from">between</label>&nbsp;<input type="text" name="booked_from" />'
    html += '&nbsp;<label for="booked_to">and</label>&nbsp;<input type="text" name="booked_to" />'
    html += '<input type="submit" name="submit" value="Add Booking"/></form>'
    return page("Bookings for %s" % drone['name'], html)

def bookings_page(environ, error_message=None):
    """Provide a list of all bookings by a user or drone, showing
    the other thing (drone or user) and the date/time
    """
    category = shift_path_info(environ)
    if not category:
        return all_bookings_page(environ, error_message)
    elif category == "user":
        return bookings_user_page(environ, error_message)
    elif category == "drone":
        return bookings_drone_page(environ, error_message)
    else:
        return "No such booking category"

def add_user(environ):
    form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ.copy(), keep_blank_values=True)
    add_user_to_database(form.getfirst("name"), form.getfirst('email_address', ""))

def add_drone(environ):
    form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ.copy(), keep_blank_values=True)
    add_drone_to_database(form.getfirst("name"), form.getfirst('location', None))

def add_booking(environ):
    form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ.copy(), keep_blank_values=True)
    try:
        add_booking_to_database(
            form.getfirst("user_id"),
            form.getfirst("drone_id"),
            form.getfirst("booked_on"),
            form.getfirst("booked_from"),
            form.getfirst("booked_to")
        )
        return True, ""
    except ValueError as e:
        return False, str(e)

def webapp(environ, start_response):
    """Serve simple pages, based on whether the URL requests
    users, drones or bookings. For now, just serve the Home page
    """
    setup_testing_defaults(environ)

    #
    # Assume we're going to serve a valid HTML page
    #
    status = '200 OK'
    headers = [('Content-type', 'text/html; charset=utf-8')]
    
    param1 = shift_path_info(environ)
    if param1 == "":
        data = index_page(environ)
    elif param1 == "users":
        data = users_page(environ)
    elif param1 == "drones":
        data = drones_page(environ)
    elif param1 == "bookings":
        data = bookings_page(environ)
    elif param1 == "add-user":
        add_user(environ)
        status = "301 Redirect"
        headers.append(("Location", "/users"))
        data = ""
    elif param1 == "add-drone":
        add_drone(environ)
        status = "301 Redirect"
        headers.append(("Location", "/drones"))
        data = ""
    elif param1 == "add-booking":
        success, error_message = add_booking(environ)
        if success:
            status = "301 Redirect"
            headers.append(("Location", environ.get("HTTP_REFERER", "/bookings")))
            data = ""
        else:
            # Get the referer URL and extract the path
            referer = environ.get("HTTP_REFERER", "")
            if "/bookings/user/" in referer:
                environ['PATH_INFO'] = "/user/" + referer.split("/user/")[1]
            elif "/bookings/drone/" in referer:
                environ['PATH_INFO'] = "/drone/" + referer.split("/drone/")[1]
            else:
                environ['PATH_INFO'] = ""  # Default to all bookings page
            data = bookings_page(environ, error_message)
    else:
        status = '404 Not Found'
        data = "Not Found: %s" % param1

    start_response(status, headers)
    return [data.encode("utf-8")]

def run_website():
    httpd = make_server('', 8000, webapp)
    print("Serving on port 8000...")
    httpd.serve_forever()

if __name__ == '__main__':
    print("About to create database %s" % DATABASE_FILEPATH)
    create_database()
    print("About to populate database %s" % DATABASE_FILEPATH)
    populate_database()
    print("About to run webserver")
    run_website()
    print("Finished")
