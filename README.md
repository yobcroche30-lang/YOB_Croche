# YOB_Crochê – Loja Online com Backend

## O que tem
- Cadastro de clientes (telefone, e-mail ou Google simplificado) + código de confirmação
- Catálogo de produtos com fotos
- Carrinho e checkout (Pix / WhatsApp)
- Entrega Uber Flex (+ R$ 5,00)
- Painel admin (produtos, pedidos, clientes)
- Banco SQLite

## Admin (acesso restrito — só você / pessoas de confiança)
- O botão **Admin NÃO aparece** no menu da loja para clientes
- Entre só pela URL: `https://seu-site.onrender.com/admin/login`
- A senha **não é mostrada** na tela de login
- Após 5 tentativas erradas, o acesso bloqueia temporariamente
- Senha padrão (troque no Render): `yob2026`
- Várias pessoas de confiança: variável `ADMIN_PASSWORDS=senha1,senha2`

## Colocar na internet (Render.com – grátis)

1. Crie conta em https://render.com
2. New → **Web Service**
3. Conecte um repositório GitHub **ou** faça upload desta pasta
4. Configurações:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Em Environment adicione:
   - `ADMIN_PASSWORD` = sua senha secreta (não compartilhe com clientes)
   - ou `ADMIN_PASSWORDS` = senha1,senha2 (você + pessoa de confiança)
   - `WHATSAPP` = 55DDDNUMERO (ex: 5511999999999)
   - `SECRET_KEY` = qualquer texto secreto longo
6. Deploy → espere 2–5 minutos
7. Abra o link tipo: `https://yob-croche.onrender.com`

## Testar no computador
```bash
pip install -r requirements.txt
python app.py
```
Abra: http://127.0.0.1:5000

## Observações
- Código de confirmação aparece na tela (modo demo). Para SMS/e-mail real, integre Twilio ou similar.
- Login Google é simplificado (nome + e-mail). OAuth completo precisa de Google Cloud Console.
- No plano grátis do Render o app “dorme” após inatividade; a primeira abertura pode demorar ~30s.
