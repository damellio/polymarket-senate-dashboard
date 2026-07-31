import os
import traceback

from flask import Flask, render_template, request, redirect, url_for
import pymysql
import pymysql.cursors
from dotenv import load_dotenv


# Load environment variables
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


app = Flask(__name__)


# Temporary debugging while deploying
@app.errorhandler(Exception)
def handle_exception(e):
    tb = traceback.format_exc()
    return f"<pre>{tb}</pre>", 500


DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'database': os.environ.get('DB_NAME'),
    'cursorclass': pymysql.cursors.DictCursor
}


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


# Convert database codes to readable labels
PARTY_LABELS = {
    'D': 'Democrat',
    'R': 'Republican',
    'L': 'Libertarian',
    'G': 'Green'
}

BUYSELL_LABELS = {
    'B': 'Buy',
    'S': 'Sell'
}


@app.template_filter('party_label')
def party_label(code):
    return PARTY_LABELS.get(code, code)


@app.template_filter('buysell_label')
def buysell_label(code):
    return BUYSELL_LABELS.get(code, code)


def get_all_races(cursor):
    cursor.execute(
        """
        SELECT RaceID, State, Position,
               CONCAT(State, ' ', Position) AS RaceName
        FROM Race
        ORDER BY State
        """
    )
    return cursor.fetchall()


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/dbcheck')
def dbcheck():
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
            race_list = get_all_races(cursor)

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
                FROM Race
                WHERE RaceID = %s
                """,
                (race_id,),
            )

            race = cursor.fetchone()

            cursor.execute(
                """
                SELECT *
                FROM Trade
                WHERE RaceID = %s
                ORDER BY StockTradeTime
                """,
                (race_id,)
            )

            trades = cursor.fetchall()

            cursor.execute(
                "SELECT * FROM Outcome WHERE RaceID = %s",
                (race_id,)
            )

            outcome = cursor.fetchone()

    finally:
        if conn:
            conn.close()

    return render_template(
        'race_detail.html',
        race=race,
        trades=trades,
        outcome=outcome
    )


# --- Trades: browse, filter, and CRUD ----------------------------

PAGE_SIZE = 50

def _trade_form_errors(form):
    """Validate trade form fields."""
    errors = []

    try:
        if float(form.get('amount', '0')) <= 0:
            errors.append("Amount must be greater than zero.")
    except ValueError:
        errors.append("Amount must be a number.")

    try:
        if int(form.get('shares', '0')) <= 0:
            errors.append("Shares must be greater than zero.")
    except ValueError:
        errors.append("Shares must be a whole number.")

    try:
        if float(form.get('price', '0')) <= 0:
            errors.append("Price must be greater than zero.")
    except ValueError:
        errors.append("Price must be a number.")

    if not form.get('race_id'):
        errors.append("Race is required.")

    return errors


@app.route('/trades/new', methods=['GET', 'POST'])
def trade_new():
    conn = None
    errors = []

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:

            race_list = get_all_races(cursor)

            if request.method == 'POST':

                errors = _trade_form_errors(request.form)

                if not errors:

                    cursor.execute(
                        """
                        INSERT INTO Trade
                            (RaceID, StockTradeTime, AccountID, BuyOrSell,
                             PartyBeingTraded, NetDirection, Amount, Shares, Price)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            request.form['race_id'],
                            request.form['trade_time'],
                            request.form['account_id'],
                            request.form['buy_sell'],
                            request.form['party_traded'],
                            request.form['net_direction'],
                            request.form['amount'],
                            request.form['shares'],
                            request.form['price'],
                        )
                    )

                    conn.commit()

                    return redirect(url_for('trades'))

    finally:
        if conn:
            conn.close()

    return render_template(
        'trade_form.html',
        mode='new',
        trade=request.form if request.method == 'POST' else {},
        races=race_list,
        errors=errors,
    )


@app.route('/trades/<int:trade_id>/edit', methods=['GET', 'POST'])
def trade_edit(trade_id):
    conn = None
    errors = []

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:

            race_list = get_all_races(cursor)

            if request.method == 'POST':

                errors = _trade_form_errors(request.form)

                if not errors:

                    cursor.execute(
                        """
                        UPDATE Trade
                        SET RaceID = %s,
                            StockTradeTime = %s,
                            AccountID = %s,
                            BuyOrSell = %s,
                            PartyBeingTraded = %s,
                            NetDirection = %s,
                            Amount = %s,
                            Shares = %s,
                            Price = %s
                        WHERE TradeID = %s
                        """,
                        (
                            request.form['race_id'],
                            request.form['trade_time'],
                            request.form['account_id'],
                            request.form['buy_sell'],
                            request.form['party_traded'],
                            request.form['net_direction'],
                            request.form['amount'],
                            request.form['shares'],
                            request.form['price'],
                            trade_id,
                        )
                    )

                    conn.commit()

                    return redirect(url_for('trades'))

                trade = request.form

            else:

                cursor.execute(
                    "SELECT * FROM Trade WHERE TradeID = %s",
                    (trade_id,)
                )

                trade = cursor.fetchone()

    finally:
        if conn:
            conn.close()

    return render_template(
        'trade_form.html',
        mode='edit',
        trade=trade,
        trade_id=trade_id,
        races=race_list,
        errors=errors,
    )


@app.route('/trades/<int:trade_id>/delete', methods=['POST'])
def trade_delete(trade_id):
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:

            cursor.execute(
                "DELETE FROM Trade WHERE TradeID = %s",
                (trade_id,)
            )

        conn.commit()

    finally:
        if conn:
            conn.close()

    return redirect(url_for('trades'))


# --- Analytics: race-level charts ----------------------------
@app.route('/analytics')
def analytics():
    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT r.RaceID,
                       CONCAT(r.State, ' ', r.Position) AS RaceName,
                       SUM(CASE WHEN t.NetDirection = 'D' THEN 1 ELSE 0 END) AS DemTrades,
                       SUM(CASE WHEN t.NetDirection = 'R' THEN 1 ELSE 0 END) AS RepTrades
                FROM Race r
                JOIN Trade t ON r.RaceID = t.RaceID
                GROUP BY r.RaceID, RaceName
                ORDER BY r.State
                """
            )

            direction_rows = cursor.fetchall()


            cursor.execute(
                """
                SELECT r.RaceID,
                       CONCAT(r.State, ' ', r.Position) AS RaceName,
                       SUM(CASE WHEN t.BuyOrSell = 'B' THEN t.Amount ELSE 0 END) AS BuyVolume,
                       SUM(CASE WHEN t.BuyOrSell = 'S' THEN t.Amount ELSE 0 END) AS SellVolume
                FROM Race r
                JOIN Trade t ON r.RaceID = t.RaceID
                GROUP BY r.RaceID, RaceName
                ORDER BY r.State
                """
            )

            volume_rows = cursor.fetchall()

    finally:
        if conn:
            conn.close()


    labels = [row['RaceName'] for row in direction_rows]
    dem_counts = [row['DemTrades'] for row in direction_rows]
    rep_counts = [row['RepTrades'] for row in direction_rows]

    buy_volume = [float(row['BuyVolume']) for row in volume_rows]
    sell_volume = [float(row['SellVolume']) for row in volume_rows]


    return render_template(
        'analytics.html',
        direction_rows=direction_rows,
        volume_rows=volume_rows,
        chart_labels=labels,
        dem_counts=dem_counts,
        rep_counts=rep_counts,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
    )


if __name__ == '__main__':
    app.run(debug=True)
