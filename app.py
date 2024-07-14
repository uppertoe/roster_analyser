from flask import Flask, render_template, request, redirect, url_for, abort
from weroster_interface import WerosterClient
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

SECRET_TOKEN = os.getenv('SECRET_TOKEN')

def verify_token(token):
    return token == SECRET_TOKEN

@app.template_filter('pluralize')
def pluralize(count, singular, plural=None):
    try:
        count = int(count)
    except (ValueError, TypeError):
        raise ValueError(f"Count must be an integer, got {type(count)}")
    if plural is None:
        plural = singular + 's'
    return singular if count == 1 else plural

@app.route('/events')
def events():
    token = request.args.get('token')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not token or not verify_token(token):
        abort(403)  # Forbidden

    # Convert date strings to datetime objects if they exist
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else None

    client = WerosterClient(start_date=start_date, end_date=end_date)
    client.login()
    events = client.assemble_events_with_registrar_counts()
    client.close_connection()
    return render_template('events.html', events=events)

@app.route('/registrars')
def registrars():
    token = request.args.get('token')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not token or not verify_token(token):
        abort(403)  # Forbidden

    # Convert date strings to datetime objects if they exist
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else None

    client = WerosterClient(start_date=start_date, end_date=end_date)
    client.login()
    registrars = client.assemble_registrar_events()
    client.close_connection()
    return render_template('registrars.html', registrars=registrars)

@app.route('/dates', methods=['GET', 'POST'])
def set_dates():
    token = request.args.get('token')
    if not token or not verify_token(token):
        abort(403)  # Forbidden
    
    # Default dates
    default_start_date = (datetime.now() - timedelta(weeks=4)).strftime("%Y-%m-%d")
    default_end_date = datetime.now().strftime("%Y-%m-%d")
    
    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        
        if 'view_events' in request.form:
            return redirect(url_for('events', token=token, start_date=start_date_str, end_date=end_date_str))
        elif 'view_registrars' in request.form:
            return redirect(url_for('registrars', token=token, start_date=start_date_str, end_date=end_date_str))
    
    return render_template('set_dates.html', default_start_date=default_start_date, default_end_date=default_end_date)

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    def generate_magic_link():
        base_url = 'http://127.0.0.1:5005'
        token = SECRET_TOKEN
        return f"{base_url}/?token={token}"

    print("Magic Link:", generate_magic_link())
    app.run(debug=True, port=5005)
