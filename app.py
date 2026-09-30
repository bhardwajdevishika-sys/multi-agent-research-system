from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_cors import CORS
from backend.routes.research_routes import research_bp, coordinator
from backend.utils.config import Config
from backend.utils.logger import logger
import os

def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY
    CORS(app) # Enable CORS for API routes
    
    # Load configuration
    app.config.from_object(Config)
    
    # Register Backend Blueprints
    app.register_blueprint(research_bp, url_prefix='/api')
    
    # --- Frontend Routes ---
    
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/dashboard')
    def dashboard():
        """
        Merged Dashboard Route.
        Uses the CoordinatorAgent's real-time status if available.
        """
        def get_timeline_step(progress):
            if progress >= 100: return 4
            if progress >= 90: return 3
            if progress >= 60: return 2
            if progress >= 30: return 1
            if progress >= 10: return 0
            return -1

        # Get real-time status from the backend coordinator
        status_data = coordinator.get_status()
        is_researching = status_data["progress"] > 0 and status_data["progress"] < 100
        topic = session.get('topic', '')
        
        # Determine current step based on coordinator progress
        current_step = {
            "progress": status_data["progress"],
            "status": status_data["status"],
            "timeline": get_timeline_step(status_data["progress"])
        }
        
        # Define agents and their statuses based on current progress
        agents = [
            {"name": "Coordinator Agent", "status": "Active" if is_researching else "Idle", "task": status_data["status"] if is_researching else "Waiting..."},
            {"name": "Research Agent", "status": "Working" if 10 <= status_data['progress'] < 30 else ("Complete" if status_data['progress'] >= 30 else "Idle"), "task": "Searching sources" if 10 <= status_data['progress'] < 30 else "Pending..."},
            {"name": "Summarizer Agent", "status": "Working" if 60 <= status_data['progress'] < 80 else ("Complete" if status_data['progress'] >= 80 else "Idle"), "task": "Synthesizing" if 60 <= status_data['progress'] < 80 else "Pending..."},
            {"name": "Verification Agent", "status": "Working" if 80 <= status_data['progress'] < 95 else ("Complete" if status_data['progress'] >= 95 else "Idle"), "task": "Validating data" if 80 <= status_data['progress'] < 95 else "Pending..."},
            {"name": "Report Generator Agent", "status": "Working" if 95 <= status_data['progress'] < 100 else ("Complete" if status_data['progress'] == 100 else "Idle"), "task": "Finalizing PDF" if 95 <= status_data['progress'] < 100 else "Pending..."}
        ]

        # Auto-refresh if research is in progress
        refresh = is_researching

        return render_template('dashboard.html', 
                               agents=agents, 
                               is_researching=is_researching, 
                               current_step=current_step,
                               topic=topic,
                               refresh=refresh)

    @app.route('/start_research', methods=['POST'])
    def start_research():
        topic = request.form.get('topic')
        if not topic:
            return redirect(url_for('dashboard'))
        
        # Store topic in session for the frontend
        session['topic'] = topic
        
        # Trigger the actual backend research logic
        # We can call the coordinator directly or via the API route logic
        import threading
        def background_research(t):
            try:
                coordinator.run_research_workflow(t)
            except Exception as e:
                logger.error(f"Background research failed: {str(e)}")

        thread = threading.Thread(target=background_research, args=(topic,))
        thread.start()
        
        return redirect(url_for('dashboard'))

    @app.route('/reset_research')
    def reset_research():
        session.pop('topic', None)
        # We could also reset the coordinator state here if needed
        coordinator.status = "Idle"
        coordinator.progress = 0
        return redirect(url_for('dashboard'))

    # Health check for the merged app
    @app.route('/health')
    def health():
        return jsonify({"status": "healthy", "mode": "merged"}), 200

    return app

# ── Module-level app instance for Gunicorn ────────────────────────────────────
# Gunicorn on Render uses: gunicorn app:app
# This creates the Flask app at import time so Gunicorn can reference it.
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    # Waitress for local Windows dev; Gunicorn handles production on Render
    if os.environ.get("FLASK_ENV") == "development":
        logger.info(f"Starting Flask dev server on port {port}")
        app.run(host="0.0.0.0", port=port, debug=True)
    else:
        try:
            from waitress import serve
            logger.info(f"Starting Waitress production server on port {port}")
            serve(app, host="0.0.0.0", port=port, threads=4)
        except ImportError:
            logger.warning("Waitress not found — falling back to Flask dev server")
            app.run(host="0.0.0.0", port=port, debug=False)
