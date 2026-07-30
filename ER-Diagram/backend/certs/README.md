# TLS Certificates

This directory holds TLS certificates for local HTTPS development.

## Setup (one-time)

1. Install mkcert:
   ```bash
   brew install mkcert  # macOS
   # or see: https://github.com/FiloSottile/mkcert#installation
   ```

2. Install local CA (one-time per machine):
   ```bash
   mkcert -install
   ```

3. Generate certificates:
   ```bash
   cd backend/certs
   mkcert localhost 127.0.0.1 ::1
   ```

This creates:
- `localhost+2.pem` - Certificate
- `localhost+2-key.pem` - Private key

## Security

- **Never commit .pem files** - they contain private keys
- Certificates are gitignored by default
- Only .gitkeep and README.md are committed
