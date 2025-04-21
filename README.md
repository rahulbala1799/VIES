# German VIES Return Generator

A Flask web application that helps generate the required file format for German VIES (VAT Information Exchange System) returns.

## Features

- Generate properly formatted VIES return files
- Simple web interface for data entry
- Validation of input data

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/german-vies.git
cd german-vies
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file based on the `env.example` provided.

## Running the Application Locally

```bash
flask run
```

The application will be available at http://localhost:5000.

## Deployment

This application is configured for deployment on Railway:

1. Push your code to GitHub
2. Connect your GitHub repository to Railway
3. Railway will automatically deploy your application

## Development

To run the application in debug mode:

```bash
flask run --debug
```

## License

[MIT](LICENSE) 