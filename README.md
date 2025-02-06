
Embedding FastAPI as an External Binary in Tauri

The following readme details all steps in taken in embedding FastAPI, using pyinstaller, into the tauri environment, such that the frontend can directly interface with the server.


## Installation

Install my-project with npm, as well as all dependencies for javascript and Python:

```bash
  npm install my-project
  cd my-project
```
It also requires the following prerequisites
```bash
  Node.js (>= 16)
  Rust (with Cargo and rustup)
  Tauri CLI (install with cargo tauri-cli)
  Python >= 3.10 (for the FastAPI backend)
  PyInstaller (to package the Python script into a binary)
```
You can simply install required python packages
## Usage/Examples
To run app in development mode
```javascript
npm run tauri dev
```


## Project Structure
These are the important project folders to understand.
```bash
/app # (frontend code, js/html/css)
/src/backend # (backend code, the "sidecar")
/src/routes # (frontend code)
/src-tauri
  |  binaries/dist/main # (compiled sidecar is put here)
  |  /icons # (app icons go here)
  |  /src/initailizers.rs # (Tauri initailization code)
  |  /src/lib.rs # (Tauri main app execution logic)
  |  /src/main.rs # ( This simply calls run() function to execute lib.rs)
  |  tauri.conf.json # (Tauri config file for app permissions. We will need to add some   
     configurations here)
package.json # (build scripts)
```
## Documentation

These were all the steps taken in developing this project. First I shall explain how to setup a project to send a GET request from the frontend, to the FastAPI server, and fetch the response.

```bash
  1) Setup Tauri Project. This was done by following Documentation provided from Tauri: 
     https://tauri.app/start/create-project/
     The options selected were: TypeScript / JavaScript ,
                                npm,
                                Svelte,
                                TypeScript

  2) Now with the basic project template created. You will have to create a backend folder 
     under your src folder. In here, you shall create a main.py. This will contain the 
     logic for the FastAPI server and is what will need to be converted to an external  
     binary.

  3) In main.py create your FastAPI code. For example, a simple get request could be
```
```typescript
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/hello")
def hello():
    return {"message": "Hello from FastAPI!"}


```
```bash
  4) You can then test the backend locally by running:
     uvicorn src/backend/main:app --reload
     This should start the FastAPI backend on http://127.0.0.1:8000.

  5) Now we update the frontend code, by updating /src/routes/+page.svelte, so that it     
     can fetch the data from FastAPI.
     This was done by having the frontend  make an asynchronous call to the FastAPI 
     backend when the button is clicked.

```
It was achieved by this function
```typescript
<script>
  let response = "";

  async function callFastApi() {
    try {
      const res = await fetch("http://localhost:8000/hello");
      if (!res.ok) throw new Error("API request failed");
      const data = await res.json();
      response = data.message;
    } catch (err) {
      response = "Error connecting to FastAPI";
    }
  }
</script>
```
```bash
  6) You then just need to link this function to when the button is clicked with the 
    following line:
    <button on:click={callFastApi}>Call FastAPI</button>

  7) Now you want to start the FastAPI server by:
    7.1) Open a terminal and navigate to your src/backend directory.
    7.2) Run the FastAPI server: uvicorn src/backend/main:app --reload
    This will start the FastAPI backend on http://127.0.0.1:8000.

  8) Finally run the Tauri project by
    8.1) In a separate terminal, navigate to the root of the Tauri project.
    8.2) Run the following command to start the Tauri app: npm run tauri dev
     This will launch the Tauri application, and you should see the message fetched from 
     FastAPI in the Svelte frontend.
```

Next we need to embed the FastAPI script as an external binary within Tauri, as follows:
```bash
  9) Navigate back to your src/backend folder. With Pyinstaller installed, you want to 
     generate the one file executable by running:
     pyinstaller --onefile main.py
     This will  bundle the FastAPI app as a binary.
     * After running pyinstaller, check the dist folder for the correct executable. Verify 
       that main-x86_64-pc-windows-msvc.exe works when you run it manually (outside of 
        After running pyinstaller, check the dist folder for the correct executable. Verify that main-x86_64-pc-windows-msvc.exe works when you run it manually (outside of Tauri) to ensure everything was bundled correctly.Tauri) to ensure everything was bundled correctly.

  10) This will create a dist folder, which will store a main file/executable. Now this 
      file needs to be renamed from main to main-x86_64-pc-windows-msvc. This is because 
      Tauri has a triple target parameter. Then move the dist folder, with the new remaned 
      main executable to src_tauri, under a new folder called "binaries". 
      So in the end you should have a file path as follows:     
      \src-tauri\binaries\dist\main-x86_64-pc-windows-msvc.exe
      Pyinstaller will also create a main spec file. Rename this file to the same naming 
      triple target naming convention and just move this file to the root folder(Though 
      this may not always be required).


  10) Next we need to configure/modify a few files.
  10.1) The first file is \src-tauri\tauri.conf.json. "To bundle the binaries of your 
        choice, you can add the externalBin property to the tauri > bundle object in your 
        tauri.conf.json." (https://v1.tauri.app/v1/guides/building/sidecar/)
        In other words, in this file you need to add the following lines:
        "externalBin": ["binaries/dist/main"], the file path here points to the 
        directory where you saved the binary executable.
  10.2) Ensure your cargo.toml saved under src_tauri has the following lines note that the
        name of the project is api_test. You will see also the file paths to lib.rs and 
        main.rs which were explained in the project structure section :
    
            [lib]
            name = "api_test_lib"
            crate-type = ["staticlib", "cdylib", "rlib"]
            path = "src/lib.rs" 

            [dependencies]
            command-group = "2.1.0"
            tauri-plugin-opener = "2.2.5"
            serde_json = "1.0"
            serde = { version = "1.0", features = ["derive"] }
            tauri = { version = "2", features = ["devtools"] }
            tauri-plugin-shell = "2"
            tauri-plugin-http = "2"

            [features]
            custom-protocol = ["tauri/custom-protocol"]

            [[bin]]
            name = "api_test" 
            path = "src/main.rs" 
  10.3) In your package.json, ensure you have the following dependencies and 
        dev-dependencies:
         "dependencies": 
         {
            "@tauri-apps/api": "^2.0.0",
            "@tauri-apps/plugin-http": "^2.0.1",
            "@tauri-apps/plugin-shell": "^2.0.1",
            "@types/node": "20.2.4",
            "@types/react": "18.2.7",
            "@types/react-dom": "18.2.4",
            "autoprefixer": "10.4.14",
            "concurrently": "^8.0.1",
            "cors": "^2.8.5",
            "eslint": "8.41.0",
            "eslint-config-next": "13.4.4",
            "next": "13.4.4",
            "postcss": "8.4.23",
            "typescript": "5.0.4"
        },
        "devDependencies": 
        {
            "@sveltejs/adapter-static": "^3.0.6",
            "@sveltejs/kit": "^2.9.0",
            "@sveltejs/vite-plugin-svelte": "^5.0.0",
            "svelte": "^5.0.0",
            "svelte-check": "^4.0.0",
            "typescript": "~5.6.2",
            "vite": "^6.0.3",
            "@tauri-apps/cli": "^2"
        }
        

```