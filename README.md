# DCOMET

DCOMET is a local P2P energy trading prototype that combines:

- a Python backend simulation and agent orchestration layer
- a React + Vite dashboard frontend

## Project Layout

```
config/
	grid_profiles/
	scenarios/
	system_config.yaml
logs/
public/
src/
	agents/
	assets/
	beckn/
	core/
	hardware/
	utils/
	api.py
	App.css
	App.jsx
	index.css
	main.jsx
tests/
main.py
requirements.txt
index.html
package.json
vite.config.js
eslint.config.js
```

## Backend Setup (Python)

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the simulation entry point:

```bash
python main.py
```

## Frontend Setup (Vite)

Install JavaScript dependencies:

```bash
npm install
```

Start dev server:

```bash
npm run dev
```

Build for production:

```bash
npm run build
```
