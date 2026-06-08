"""Launch the Sherloq web API and browser UI."""

import uvicorn


def main():
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
