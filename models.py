# models.py
from main import db

class Automation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    automation_type = db.Column(db.String(20), nullable=False)  # 'value' or 'time'
    variable = db.Column(db.String(50))  # For value-based automations
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    trigger_time = db.Column(db.Time)  # For time-based automations
    action = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    last_triggered = db.Column(db.DateTime)
