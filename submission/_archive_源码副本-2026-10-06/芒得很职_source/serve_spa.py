"""启动 SPA 预览服务器（解决后端路由问题）"""
import http.server, socketserver, os, sys, threading, webbrowser

PORT = 5173
DIST_DIR = os.path.join(os.path.dirname(__file__), "dist")

class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.lstrip('/').split('?')[0].split('#')[0]
        full = os.path.join(os.getcwd(), path)
        if os.path.isfile(full):
            return super().do_GET()
        self.path = '/index.html'
        return super().do_GET()
    def log_message(self, fmt, *args):
        print(f"[SPA] {args[0]} {args[1]} {args[2]}")

os.chdir(DIST_DIR)
server = socketserver.TCPServer(("127.0.0.1", PORT), SPAHandler)
print(f"✅ SPA 预览服务器: http://127.0.0.1:{PORT}")
print(f"   按 Ctrl+C 停止")
server.serve_forever()