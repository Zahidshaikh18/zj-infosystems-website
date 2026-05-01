from flask import Flask, render_template, request, session, redirect, url_for, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
import smtplib
from email.mime.text import MIMEText
from functools import wraps
from datetime import timedelta, timezone, datetime
from collections import defaultdict
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("app_secret_key")
app.permanent_session_lifetime = timedelta(minutes=30)

client = MongoClient(os.getenv("mongo_uri"))

attendance_db = client["attendance_db"]
attendance_collection = attendance_db["records"]

add_edit_db = client["company"]
employee_collection = add_edit_db["employees"]
client_collection = client["company"]["clients"]

contact_db = client["contact_db"]
contact_collection = contact_db["contact_messages"]


def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            flash("Access denied. Please log in as admin.", "warning")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/solutions")
def solutions():
    return render_template("solution.html")


@app.route("/people")
def people():
    return redirect("https://www.linkedin.com/company/zj-infosystems-india-private-limited/people/")


@app.route("/get_in_touch", methods=["GET", "POST"])
def get_in_touch():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        company = request.form.get("company")
        phone = request.form.get("phone")
        service = request.form.get("service")
        message = request.form.get("message")

        subject = f"New Contact Form Submission from {name}"
        body = f"""
            Name: {name}
            Email: {email}
            Company: {company}
            Phone: {phone}
            Service Interested: {service}
            Message: {message}
            """
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = os.getenv("mail_email")
        msg['To'] = os.getenv("mail_email")

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(os.getenv("mail_email"), os.getenv("mail_password"))
                smtp.send_message(msg)

            contact_collection.insert_one({
                "name": name,
                "email": email,
                "company": company,
                "phone": phone,
                "service": service,
                "message": message,
                "submitted_at": datetime.now(timezone.utc)
            })

            flash("Message was sent successfully!", category="success")
        except Exception as e:
            print("Error sending email:", e)
            flash("There was an error. Please try again later.", category="danger")

        return redirect(url_for("get_in_touch"))

    return render_template("get_in_touch.html")


@app.route("/login", methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")

        if username == os.getenv("admin_username") and password == os.getenv("admin_password"):
            session['admin'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid username or password", "danger")
            return redirect(url_for('admin_login'))

    return render_template("login.html")


@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('admin_login'))


@app.route("/admin-dashboard", methods=['GET'])
@admin_login_required
def admin_dashboard():
    clients = client_collection.find()
    monthly_counts = defaultdict(int)

    for client in clients:
        created_at = client.get("created_at")
        if created_at:
            month_key = created_at.strftime("%Y-%m")
            monthly_counts[month_key] += 1

    sorted_months = sorted(monthly_counts)
    client_month_labels = sorted_months
    client_counts = [monthly_counts[month] for month in sorted_months]

    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    status_list = ['Present', 'Absent', 'On Leave', 'Late']

    data = {status: [0] * 7 for status in status_list}

    records = attendance_collection.find()

    for record in records:
        date_str = record.get('date')
        status = record.get('status')

        if date_str and status in data:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception as e:
                print(f"ERROR parsing date: {date_str} => {e}")
                continue

            weekday_index = date_obj.weekday()
            data[status][weekday_index] += 1

    present_counts = data['Present']
    absent_counts = data['Absent']
    leave_counts = data['On Leave']
    late_counts = data['Late']

    return render_template(
        'admin_dashboard.html',
        labels=weekdays,
        present_counts=present_counts,
        absent_counts=absent_counts,
        leave_counts=leave_counts,
        late_counts=late_counts,
        client_month_labels=client_month_labels,
        client_counts=client_counts
    )


@app.route('/attendance', methods=['GET', 'POST'])
@admin_login_required
def attendance():
    if request.method == 'POST':
        name = request.form.get('name')
        status = request.form.get('status')
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        date = now.date().isoformat()
        weekday = now.strftime("%A")

        attendance_collection.insert_one({
            'name': name,
            'status': status,
            'date': date,
            'weekday': weekday,
            'timestamp': timestamp
        })

        return redirect(url_for('attendance'))

    employees = employee_collection.find({}, {"_id": 0, "name": 1})
    employee_names = [emp["name"] for emp in employees]

    records = attendance_collection.find().sort('timestamp', -1)
    return render_template('attendance.html', records=records, employee_names=employee_names)


@app.route('/delete-attendance/<id>', methods=['POST'])
def delete_attendance(id):
    attendance_collection.delete_one({"_id": ObjectId(id)})
    flash("Attendance record deleted successfully!", "info")
    return redirect(url_for('attendance'))


@app.route('/add_edit', methods=['GET', 'POST'])
@admin_login_required
def add_edit():
    if request.method == "POST":
        data = {
            "name": request.form["name"],
            "position": request.form["position"],
            "department": request.form["department"],
            "email": request.form["email"],
            "contact": request.form["contact"],
        }

        if "_id" in request.form and request.form["_id"]:
            employee_collection.update_one(
                {"_id": ObjectId(request.form["_id"])},
                {"$set": data}
            )
            flash("Employee updated successfully!", "info")
        else:
            employee_collection.insert_one(data)
            flash("Employee added successfully!", "success")

        return redirect(url_for("add_edit"))

    all_employees = list(employee_collection.find())
    return render_template("add_edit.html", employees=all_employees, employee=None)


@app.route('/edit-employee/<id>', methods=['GET', 'POST'])
def edit_employee(id):
    employee = employee_collection.find_one({"_id": ObjectId(id)})
    employees = list(employee_collection.find())
    return render_template('add_edit.html', employees=employees, employee=employee)


@app.route('/delete-employee/<id>')
def delete_employee(id):
    employee_collection.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('add_edit'))


@app.route("/clients", methods=["GET", "POST"])
@admin_login_required
def clients():
    if request.method == "POST":
        data = {
            "name": request.form["name"],
            "email": request.form["email"],
            "company": request.form["company"],
            "phone": request.form["phone"],
            "services": request.form.getlist("services"),
            "created_at": datetime.now(timezone.utc)
        }

        if "_id" in request.form and request.form["_id"]:
            client_collection.update_one(
                {"_id": ObjectId(request.form["_id"])},
                {"$set": data}
            )
            flash("Client updated successfully!", "info")
        else:
            client_collection.insert_one(data)
            flash("Client added successfully!", "success")

        return redirect(url_for("clients"))

    all_clients = list(client_collection.find())
    return render_template("clients.html", clients=all_clients, client=None)


@app.route("/edit-client/<id>")
def edit_client(id):
    client = client_collection.find_one({"_id": ObjectId(id)})
    clients = list(client_collection.find())
    return render_template("clients.html", clients=clients, client=client)


@app.route("/delete-client/<id>")
def delete_client(id):
    client_collection.delete_one({"_id": ObjectId(id)})
    flash("Client deleted successfully!", "warning")
    return redirect(url_for("clients"))


@app.route("/contacts", methods=["GET"])
@admin_login_required
def view_contacts():
    contacts = contact_collection.find().sort("timestamp", -1)
    return render_template("contacts.html", contacts=contacts)


if __name__ == "__main__":
    app.run(debug=True, port=4545
            )

