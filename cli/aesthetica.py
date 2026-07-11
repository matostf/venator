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
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Venator Aesthetica | Curadoria Visual</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --glass-bg: rgba(15, 15, 20, 0.75);
            --glass-border: rgba(255, 255, 255, 0.08);
        }
        body {
            margin: 0;
            padding: 0;
            background-color: #050505;
            color: #eaeaea;
            font-family: 'Outfit', sans-serif;
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            user-select: none;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        #bg-blur {
            position: absolute;
            top: -5%; left: -5%; width: 110%; height: 110%;
            background-size: cover;
            background-position: center;
            filter: blur(50px) brightness(0.25);
            z-index: 0;
            transition: background-image 0.6s ease;
        }
        #image-container {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1;
            padding-bottom: 160px; /* Espaço para a UI flutuante */
            box-sizing: border-box;
        }
        img {
            max-width: 95%;
            max-height: 95%;
            object-fit: contain;
            border-radius: 6px;
            box-shadow: 0 25px 60px rgba(0,0,0,0.8);
            transition: opacity 0.4s ease, transform 0.4s ease;
        }
        #ui-layer {
            position: absolute;
            bottom: 40px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 10;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
            width: 90%;
            max-width: 700px;
        }
        .glass-panel {
            background: var(--glass-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 20px 40px;
            width: 100%;
            box-sizing: border-box;
            text-align: center;
            box-shadow: 0 15px 35px rgba(0,0,0,0.6);
        }
        h1 { 
            margin: 0 0 6px 0; 
            font-size: 22px; 
            font-weight: 600; 
            color: #ffffff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        p { 
            margin: 0; 
            color: #aaaaaa; 
            font-size: 15px; 
            font-weight: 300; 
        }
        .controls {
            display: flex;
            gap: 20px;
            justify-content: center;
            width: 100%;
        }
        button {
            border: none;
            border-radius: 50px;
            padding: 15px 35px;
            font-size: 15px;
            font-weight: 600;
            font-family: 'Outfit', sans-serif;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
            display: flex;
            align-items: center;
            gap: 10px;
            width: 180px;
            justify-content: center;
        }
        button:hover { transform: translateY(-4px); }
        button:active { transform: translateY(1px); }
        .btn-discard { 
            background: rgba(255, 69, 58, 0.1); 
            color: #ff453a; 
            border: 1px solid rgba(255, 69, 58, 0.25); 
        }
        .btn-discard:hover { background: rgba(255, 69, 58, 0.2); box-shadow: 0 8px 25px rgba(255, 69, 58, 0.25); }
        
        .btn-preserve { 
            background: rgba(50, 215, 75, 0.1); 
            color: #32d74b; 
            border: 1px solid rgba(50, 215, 75, 0.25); 
        }
        .btn-preserve:hover { background: rgba(50, 215, 75, 0.2); box-shadow: 0 8px 25px rgba(50, 215, 75, 0.25); }
        
        .btn-superlike { 
            background: rgba(255, 204, 0, 0.1); 
            color: #ffcc00; 
            border: 1px solid rgba(255, 204, 0, 0.25); 
        }
        .btn-superlike:hover { background: rgba(255, 204, 0, 0.2); box-shadow: 0 8px 25px rgba(255, 204, 0, 0.25); }
        
        .loading { opacity: 0; transform: scale(0.97); }
        
        .hint { font-size: 13px; color: #666; margin-top: 5px; font-weight: 300;}
    </style>
</head>
<body>
    <div id="bg-blur"></div>
    <div id="image-container">
        <img id="painting" src="" style="display:none;" />
    </div>
    <div id="ui-layer">
        <div class="glass-panel">
            <h1 id="title">Conectando ao oráculo...</h1>
            <p id="artist">Aguarde, as musas estão buscando obras de arte...</p>
        </div>
        <div class="controls">
            <button class="btn-discard" onclick="vote('discard')">❌ Descartar</button>
            <button class="btn-superlike" onclick="vote('superlike')">⭐ Superlike</button>
            <button class="btn-preserve" onclick="vote('preserve')">✅ Preservar</button>
        </div>
        <div class="hint">Use as Setas ⬅️ (Descartar), ➡️ (Preservar) e ⬆️ (Superlike)</div>
    </div>

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
                    document.getElementById('artist').innerText = "Não há mais obras por agora.";
                    return;
                }
                
                currentImage = data;
                
                const img = document.getElementById('painting');
                const bgBlur = document.getElementById('bg-blur');
                
                let cleanTitle = data.title.replace(/\.[a-zA-Z0-9]+$/, '').replace(/_/g, ' ');
                
                img.onload = () => { 
                    img.classList.remove('loading'); 
                    img.style.display = 'block'; 
                    bgBlur.style.backgroundImage = `url('${data.display_url}')`;
                };
                img.src = data.display_url;
                
                document.getElementById('title').innerText = cleanTitle;
                document.getElementById('title').title = cleanTitle; 
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
            if (e.key === 'ArrowUp') vote('superlike');
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
    current_offset = 0
    
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
                image['priority'] = 'normal'
                self.save_to_thesaurus(image)
                print(f" ✅ [PRESERVADA] -> {image.get('title')}")
            elif action == 'superlike':
                image['priority'] = 'superlike'
                self.save_to_thesaurus(image)
                print(f" ⭐ [SUPERLIKE]  -> {image.get('title')}")
            else:
                print(f" ❌ [DESCARTADA] -> {image.get('title')}")
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            
    def fetch_more_from_wikimedia(self):
        seed = "Classical history painting"
        offset = self.__class__.current_offset
        url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(seed)}&gsrnamespace=6&gsrlimit=20&gsroffset={offset}&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=1200&format=json"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'VenatorAesthetica/1.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                pages = data.get('query', {}).get('pages', {})
                
                for page_id, page_info in pages.items():
                    imageinfo = page_info.get('imageinfo', [{}])[0]
                    ext = imageinfo.get('extmetadata', {})
                    
                    title = page_info.get('title', '').replace('File:', '')
                    
                    # Filtra apenas imagens (ignora livros em PDF, TIF ou DjVu que quebram a tag <img>)
                    lower_title = title.lower()
                    if lower_title.endswith('.pdf') or lower_title.endswith('.djvu') or lower_title.endswith('.tif') or lower_title.endswith('.tiff'):
                        continue
                    
                    artist_html = ext.get('Artist', {}).get('value', 'Autor Desconhecido')
                    import re
                    artist_clean = re.sub(r'<[^>]+>', '', artist_html).strip()
                    if not artist_clean: artist_clean = "Autor Desconhecido"
                    
                    self.__class__.images_queue.append({
                        "id": page_id,
                        "title": title,
                        "artist": artist_clean,
                        "original_url": imageinfo.get('url', ''),
                        "display_url": imageinfo.get('thumburl', imageinfo.get('url', '')),
                        "source": "wikimedia_commons",
                        "license": ext.get('LicenseShortName', {}).get('value', 'Desconhecida')
                    })
                
                # Avança a página para a próxima busca
                self.__class__.current_offset += 20
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
