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
        // 1. Sincronizar archivos al disco virtual
        let localModules = [];
        files.forEach(f => {
            try { 
                pyodide.FS.writeFile(f.name, f.content); 
                if(f.name.endsWith('.py')) localModules.push(`'${f.name.replace('.py', '')}'`);
            } catch(e){}
        });

        // 2. Interceptor de Consola en Tiempo Real y Entradas Síncronas
        const setup = `
import sys, builtins, js

# Limpieza de caché local
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

        // 4. Leer archivos resultantes y devolver al Main
        let outFiles = [];
        for (const name of pyodide.FS.readdir('.')) {
            if (name !== '.' && name !== '..' && !pyodide.FS.isDir(pyodide.FS.stat(name).mode)) {
                outFiles.push({ name, content: pyodide.FS.readFile(name, {encoding: "utf8"})});
            }
        }
        postMessage({ type: "run_done", files: outFiles });

    } catch (err) {
        // 5. Gestor de Instalación a Demanda Mágico
        const errMsg = err.message;
        const match = errMsg.match(/ModuleNotFoundError: No module named '([^']+)'/);
        
        if (match && match[1] && retryCount < 5) {
            const missingPkg = match[1];
            if (files.some(f => f.name === `${missingPkg}.py`)) { postMessage({ type: "run_error", error: errMsg }); return; }

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