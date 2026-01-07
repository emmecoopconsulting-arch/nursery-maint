# Nursery Maintenance (QR + Interventi + Checklist)

Webapp Django pronta per:
- Sedi
- Asset (attrezzature/arredi) con QR generato dall'app
- Interventi programmati + checklist (SI/NO, numero, testo, foto)
- Etichette PDF stampabili

## Avvio rapido (locale)
1. Copia `.env.example` in `.env` e compila i valori (soprattutto `DJANGO_SECRET_KEY` e `BASE_URL`)
2. (Opzionale) punta il DB al tuo PostgreSQL/MariaDB su Proxmox
3. Avvia:
   ```bash
   docker compose up --build
   ```

## Primo accesso
- Admin: `/admin/`
- Crea un superuser:
  ```bash
  docker compose exec web python manage.py createsuperuser
  ```

## QR
- Il QR contiene un URL tipo: `/a/<token>`
- La pagina asset (da QR) è `/a/<token>`
- PNG QR: `/asset/<id>/qr.png`
- Etichetta PDF: `/asset/<id>/label.pdf`

## Deploy su Coolify
- Importa questo repo
- Imposta le env come nel `.env`
- Aggiungi volume persistente per `/app/media`
- Punta al DB su Proxmox

## Healthcheck
- `/healthz` ritorna `ok`
