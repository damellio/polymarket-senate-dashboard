import os
import traceback
from flask import Flask, render_template
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

# Load .env from this file's own folder, regardless of what working
# directory Passenger/WSGI happens to launch the app from.
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)


# TEMPORARY debug helper: show the real Python traceback in the browser
# instead of a generic 500 page. This bypasses the need to find/configure
# Passenger's log file. Remove this once the app is further along --
# showing raw tracebacks to site visitors is not something you'd want
# in a real production app.
@app.errorhandler(Exception)
def handle_exception(e):
    tb = traceback.format_exc()
    return f"<pre>{tb}</pre>", 500

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    # Railway's shared MySQL instance listens on a non-default port -- the
    # original config had no 'port' key at all, which silently fell back to
    # MySQL's default of 3306 and could never reach a Railway proxy host.
    'port': int(os.environ.get('DB_PORT', 3306)),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'database': os.environ.get('DB_NAME'),
    'cursorclass': pymysql.cursors.DictCursor
}


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


# --- Display helpers -------------------------------------------------
# The live schema stores several fields as single-character codes
# (B/S, D/R/L/G) to keep the tables compact. These lookups turn those
# codes into readable labels for the templates without changing the
# underlying data.
PARTY_LABELS = {'D': 'Democrat', 'R': 'Republican', 'L': 'Libertarian', 'G': 'Green'}
BUYSELL_LABELS = {'B': 'Buy', 'S': 'Sell'}


@app.template_filter('party_label')
def party_label(code):
    return PARTY_LABELS.get(code, code)


@app.template_filter('buysell_label')
def buysell_label(code):
    return BUYSELL_LABELS.get(code, code)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/dbcheck')
def dbcheck():
    """Temporary diagnostic route -- shows what config loaded and whether
    the database connection succeeds. Remove this once things are working
    and the real app is further along, since it's not meant for production."""
    info = {
        'DB_HOST': os.environ.get('DB_HOST'),
        'DB_PORT': os.environ.get('DB_PORT'),
        'DB_USER': os.environ.get('DB_USER'),
        'DB_NAME': os.environ.get('DB_NAME'),
        'DB_PASSWORD_IS_SET': bool(os.environ.get('DB_PASSWORD')),
    }
    try:
        conn = get_db_connection()
        conn.close()
        info['connection'] = 'SUCCESS'
    except Exception as e:
        info['connection'] = 'FAILED'
        info['error'] = str(e)
    return info


@app.route('/races')
def races():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # The Race table has no RaceName/OfficePosition columns --
            # RaceName is built from State + Position, same as Milestone 2's
            # "race list" query.
            cursor.execute(
                """
                SELECT RaceID, State, Position,
                       CONCAT(State, ' ', Position) AS RaceName
                FROM Race
                ORDER BY State
                """
            )
            race_list = cursor.fetchall()
    finally:
        if conn:
            conn.close()
    return render_template('races.html', races=race_list)


@app.route('/race/<int:race_id>')
def race_detail(race_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *, CONCAT(State, ' ', Position) AS RaceName
                FROM Race WHERE RaceID = %s
                """,
                (race_id,),
            )
            race = cursor.fetchone()

            # StockTradeTime is the live column name (the proposal's
            # TradeTimestamp never made it into the implemented schema).
            cursor.execute(
                "SELECT * FROM Trade WHERE RaceID = %s ORDER BY StockTradeTime", (race_id,)
            )
            trades = cursor.fetchall()

            cursor.execute("SELECT * FROM Outcome WHERE RaceID = %s", (race_id,))
            outcome = cursor.fetchone()
    finally:
        if conn:
            conn.close()
    return render_template('race_detail.html', race=race, trades=trades, outcome=outcome)


if __name__ == '__main__':
    app.run(debug=True)
