importScripts("https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js");

let pyodide = null;
let inputInt32View = null;
let inputEncodedView = null;

async function init() {
    pyodide = await loadPyodide();
    postMessage({ type: "init_done" });
}
init();

// Funciones puente para Python
self.post_print = (text, color) => postMessage({ type: "print", text, color });
self.post_request_input = () => postMessage({ type: "request_input" });
self.wait_for_input = () => Atomics.wait(inputInt32View, 0, 0); // Bloquea el hilo hasta que el usuario escriba
self.read_input_from_buffer = () => {
    const length = inputInt32View[0];
    const decoder = new TextDecoder();
    const text = decoder.decode(inputEncodedView.slice(0, length));
    Atomics.store(inputInt32View, 0, 0); // Reseteamos el buffer
    return text;
};

async function executeCode(code, files, retryCount = 0) {
    try {
        // 1. Sincronizar archivos al disco virtual con subcarpetas
        let localModules = [];
        
        function getFullPath(filesArray, fileObj) {
            if (!fileObj.parentId) return fileObj.name;
            const parent = filesArray.find(f => f.id === fileObj.parentId);
            return parent ? getFullPath(filesArray, parent) + '/' + fileObj.name : fileObj.name;
        }

        files.forEach(f => {
            try {
                const fullPath = getFullPath(files, f);
                const parts = fullPath.split('/');
                
                let currentPath = "";
                for (let i = 0; i < parts.length - 1; i++) {
                    currentPath += (currentPath ? "/" : "") + parts[i];
                    try { pyodide.FS.mkdir(currentPath); } catch (e) {} 
                    // Auto-crear __init__.py para que Python lo reconozca como módulo
                    try { pyodide.FS.writeFile(currentPath + '/__init__.py', ''); } catch (e) {} 
                }

                // Escribir el archivo real
                pyodide.FS.writeFile(fullPath, f.content);
                
                // Si es Python, lo guardamos para limpiar su caché luego
                if (fullPath.endsWith('.py')) {
                    localModules.push(`'${fullPath.replace(/\.py$/, '').replace(/\//g, '.')}'`);
                }
            } catch(e) { console.error(e); }
        });

        // 2. Interceptor de Consola en Tiempo Real y Entradas Síncronas
        const setup = `
import sys, builtins, js
if "." not in sys.path: sys.path.append(".")

# Limpieza de caché local para que los imports reflejen los cambios
for mod in [${localModules.join(',')}] :
    if mod in sys.modules: del sys.modules[mod]

class RealtimeWriter:
    def __init__(self, color):
        self.color = color
        self.buf = ""
    def write(self, text):
        self.buf += text
        if '\\n' in self.buf:
            lines = self.buf.split('\\n')
            for line in lines[:-1]: js.post_print(line, self.color)
            self.buf = lines[-1]
    def flush(self): 
        if self.buf: js.post_print(self.buf, self.color); self.buf = ""

sys.stdout = RealtimeWriter("output")
sys.stderr = RealtimeWriter("error")

def custom_input(prompt_text=""):
    if prompt_text: js.post_print(prompt_text, "ai")
    js.post_request_input()
    js.wait_for_input()
    ans = js.read_input_from_buffer()
    js.post_print("> " + ans, "output")
    return ans

builtins.input = custom_input
`;
        // 3. Cargar y Ejecutar
        const fullCode = setup + "\n" + code;
        await pyodide.loadPackagesFromImports(fullCode);
        await pyodide.runPythonAsync(fullCode);
        
        pyodide.runPython("sys.stdout.flush(); sys.stderr.flush()");

        // 4. Leer archivos resultantes (recursivamente) y devolver al navegador (ide.html)
        let outFiles = [];
        
        function readDirRecursively(dirPath) {
            const items = pyodide.FS.readdir(dirPath);
            for (const name of items) {
                if (name === '.' || name === '..' || name.startsWith('__pycache__')) continue;
                
                const fullPath = dirPath === '.' ? name : dirPath + '/' + name;
                const stat = pyodide.FS.stat(fullPath);
                
                if (pyodide.FS.isDir(stat.mode)) {
                    readDirRecursively(fullPath);
                } else {
                    // Ignorar los __init__.py vacíos que creamos nosotros por debajo
                    if (name === '__init__.py') continue;
                    outFiles.push({ name: fullPath, content: pyodide.FS.readFile(fullPath, {encoding: "utf8"})});
                }
            }
        }
        
        readDirRecursively('.');
        postMessage({ type: "run_done", files: outFiles });

    } catch (err) {
        // 5. Gestor de Instalación a Demanda Mágico
        const errMsg = err.message;
        const match = errMsg.match(/ModuleNotFoundError: No module named '([^']+)'/);
        
        if (match && match[1] && retryCount < 5) {
            const missingPkg = match[1];
            // Si el módulo que falta es un archivo nuestro, no intentamos instalarlo de pip
            if (files.some(f => f.name === `${missingPkg}.py` || f.name.includes(`${missingPkg}/`))) { 
                postMessage({ type: "run_error", error: errMsg }); 
                return; 
            }

            postMessage({ type: "installing", pkg: missingPkg });
            try {
                await pyodide.loadPackage("micropip");
                await pyodide.pyimport("micropip").install(missingPkg);
                postMessage({ type: "print", text: `[System] Package '${missingPkg}' installed. Resuming...`, color: "ai" });
                await executeCode(code, files, retryCount + 1);
            } catch(e) {
                postMessage({ type: "run_error", error: `[System] Failed to install '${missingPkg}'. Details: ${e.message.split('\\n').slice(-2).join(' ')}` });
            }
        } else {
            postMessage({ type: "run_error", error: errMsg });
        }
    }
}

self.onmessage = async (e) => {
    if (e.data.type === "init") {
        inputInt32View = new Int32Array(e.data.buffer, 0, 1);
        inputEncodedView = new Uint8Array(e.data.buffer, 4);
        Atomics.store(inputInt32View, 0, 0);
    } else if (e.data.type === "run") {
        await executeCode(e.data.code, e.data.files);
    }
};