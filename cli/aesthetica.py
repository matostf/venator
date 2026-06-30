import sys
import os
import json
import webbrowser
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==============================================================================
# HTML e CSS Embutido (Design Dark Mode inspirado em uma galeria de arte)
# ==============================================================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Venator Aesthetica | Curadoria Visual</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #0d0d0f;
            color: #eaeaea;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            height: 100vh;
            overflow: hidden;
            user-select: none;
        }
        #image-container {
            flex-grow: 1;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 40px;
            box-sizing: border-box;
            position: relative;
        }
        img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border-radius: 4px;
            box-shadow: 0 15px 40px rgba(0,0,0,0.8);
            transition: opacity 0.4s ease;
        }
        #metadata {
            text-align: center;
            padding: 0 20px 20px 20px;
            max-width: 900px;
            z-index: 10;
        }
        h1 { margin: 0 0 5px 0; font-size: 26px; font-weight: 400; color: #f2f2f2; }
        p { margin: 0; color: #b3b3b3; font-size: 16px; font-weight: 300; }
        .controls {
            display: flex;
            gap: 30px;
            padding: 30px 40px;
            background: linear-gradient(to top, rgba(13,13,15,1) 40%, rgba(13,13,15,0));
            width: 100%;
            justify-content: center;
            z-index: 10;
        }
        button {
            border: none;
            border-radius: 50px;
            padding: 16px 45px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
            text-transform: uppercase;
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        button:hover { transform: translateY(-3px); filter: brightness(1.15); box-shadow: 0 10px 20px rgba(0,0,0,0.3); }
        button:active { transform: translateY(1px); }
        .btn-discard { background-color: #2c2c30; color: #ff453a; border: 1px solid #ff453a33; }
        .btn-preserve { background-color: #32d74b11; color: #32d74b; border: 1px solid #32d74b44; }
        .loading { opacity: 0.1; }
        
        .hint { font-size: 12px; color: #555; position: absolute; bottom: 10px; right: 20px; }
    </style>
</head>
<body>
    <div id="image-container">
        <img id="painting" src="" style="display:none;" />
    </div>
    <div id="metadata">
        <h1 id="title">Conectando ao oráculo...</h1>
        <p id="artist">Aguarde, as musas estão buscando obras de arte...</p>
    </div>
    <div class="controls">
        <button class="btn-discard" onclick="vote('discard')">❌ Descartar</button>
        <button class="btn-preserve" onclick="vote('preserve')">✅ Preservar</button>
    </div>
    <div class="hint">Use as Setas ⬅️ e ➡️ do teclado</div>

    <script>
        let currentImage = null;
        let isProcessing = false;

        async function loadNext() {
            document.getElementById('painting').classList.add('loading');
            try {
                const response = await fetch('/api/next');
                const data = await response.json();
                
                if (data.error) {
                    document.getElementById('title').innerText = "Fim da Galeria";
                    document.getElementById('artist').innerText = "Não há mais obras por agora. Retorne mais tarde.";
                    return;
                }
                
                currentImage = data;
                
                const img = document.getElementById('painting');
                let cleanTitle = data.title.replace(/\\.[a-zA-Z0-9]+$/, '').replace(/_/g, ' ');
                if (cleanTitle.length > 80) cleanTitle = cleanTitle.substring(0, 80) + '...';
                
                img.onload = () => { 
                    img.classList.remove('loading'); 
                    img.style.display = 'block'; 
                };
                img.src = data.url;
                
                document.getElementById('title').innerText = cleanTitle;
                document.getElementById('artist').innerText = data.artist || "Autor Desconhecido";
            } catch (e) {
                console.error(e);
            } finally {
                isProcessing = false;
            }
        }

        async function vote(action) {
            if (!currentImage || isProcessing) return;
            isProcessing = true;
            
            document.getElementById('painting').classList.add('loading');
            
            try {
                await fetch('/api/vote', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: action, image: currentImage })
                });
                loadNext();
            } catch (e) {
                console.error(e);
                isProcessing = false;
            }
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') vote('discard');
            if (e.key === 'ArrowRight') vote('preserve');
        });

        loadNext();
    </script>
</body>
</html>
"""

# ==============================================================================
# Servidor Python Ultraleve
# ==============================================================================
class AestheticaHandler(BaseHTTPRequestHandler):
    images_queue = []
    
    def log_message(self, format, *args):
        pass 
        
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            
        elif self.path == '/api/next':
            if not self.__class__.images_queue:
                self.fetch_more_from_wikimedia()
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            if self.__class__.images_queue:
                img = self.__class__.images_queue.pop(0)
                self.wfile.write(json.dumps(img).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({"error": "No more images found"}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/vote':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            action = data.get('action')
            image = data.get('image')
            
            if action == 'preserve':
                self.save_to_thesaurus(image)
                print(f" ✅ [PRESERVADA no Thesaurus] -> {image.get('title')}")
            else:
                print(f" ❌ [DESCARTADA]              -> {image.get('title')}")
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            
    def fetch_more_from_wikimedia(self):
        seed = "Classical history painting"
        url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(seed)}&gsrnamespace=6&gsrlimit=20&prop=imageinfo&iiprop=url|extmetadata&format=json"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'VenatorAesthetica/1.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                pages = data.get('query', {}).get('pages', {})
                
                for page_id, page_info in pages.items():
                    imageinfo = page_info.get('imageinfo', [{}])[0]
                    ext = imageinfo.get('extmetadata', {})
                    
                    title = page_info.get('title', '').replace('File:', '')
                    
                    artist_html = ext.get('Artist', {}).get('value', 'Autor Desconhecido')
                    import re
                    artist_clean = re.sub(r'<[^>]+>', '', artist_html).strip()
                    if not artist_clean: artist_clean = "Autor Desconhecido"
                    
                    self.__class__.images_queue.append({
                        "id": page_id,
                        "title": title,
                        "artist": artist_clean,
                        "url": imageinfo.get('url', ''),
                        "source": "wikimedia_commons",
                        "license": ext.get('LicenseShortName', {}).get('value', 'Desconhecida')
                    })
        except Exception as e:
            print(f"\\n[!] Erro ao invocar as musas (Wikimedia): {e}")

    def save_to_thesaurus(self, image):
        thesaurus_dir = os.path.expanduser("~/Projetos/thesaurus/data")
        os.makedirs(thesaurus_dir, exist_ok=True)
        manifest_path = os.path.join(thesaurus_dir, "curadoria_aesthetica.json")
        
        saved = []
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
            except:
                pass
                
        if not any(img.get('id') == image.get('id') for img in saved):
            saved.append(image)
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(saved, f, ensure_ascii=False, indent=4)

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, AestheticaHandler)
    url = f"http://localhost:{port}"
    
    print(f"\\n" + "="*60)
    print(f" 🏛️  VENATOR AESTHETICA - Motor de Curadoria Visual")
    print(f"    Portão de Acesso: {url}")
    print(f"="*60)
    print(f"\\nO seu navegador está sendo aberto. Use as setas Direita e Esquerda")
    print(f"para julgar as obras. As aprovações vão direto para o Thesaurus.\\n")
    print(f"[Pressione Ctrl+C para encerrar o servidor e fechar a galeria]\\n")
    
    webbrowser.open(url)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\\n\\nGaleria fechada. Bom descanso, mestre curador.\\n")
        sys.exit(0)

if __name__ == '__main__':
    run()
