"""Local/LAN launcher. Use Compose + HTTPS for the public internet."""
import argparse
from pathlib import Path
from waitress import serve
from app import create_app

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lan', action='store_true', help='Allow connections from the local network')
    parser.add_argument('--port', type=int, default=8081)
    args = parser.parse_args()
    app = create_app()
    host = '0.0.0.0' if args.lan else '127.0.0.1'
    print(f'Players: http://127.0.0.1:{args.port}/\nAdmin:   http://127.0.0.1:{args.port}/admin', flush=True)
    print(f'Local password (unless ORBIT_ADMIN_PASSWORD is set): {Path(app.config["DATABASE"]).resolve().parent / "admin.password"}', flush=True)
    serve(app, host=host, port=args.port, threads=8)
