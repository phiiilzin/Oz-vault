# Oz Store

Loja online (Flask + SQLite) baseada no conteúdo real do servidor Discord
"Oz Vault", com a estrutura de navegação inspirada na MYU Store.

## Rodando localmente (Termux / qualquer Linux)

```bash
pip install -r requirements.txt --break-system-packages
python app.py
```

Acesse: http://localhost:5000

O banco `oz_store.db` é criado automaticamente na primeira execução, já
populado com as categorias, produtos e avaliações reais coletados do
Discord.

## Painel administrativo

URL: `/admin/login`

- Usuário: `admin`
- Senha: `oz2026admin`

**Troque essa senha assim que possível** (crie um novo admin com hash de
senha e remova/edite o registro padrão na tabela `admins`).

## Deploy no Render

1. Suba o projeto num repositório GitHub.
2. Crie um "Web Service" no Render apontando para o repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `python app.py`
5. Defina a variável de ambiente `SECRET_KEY` com um valor aleatório forte.

⚠️ **Atenção**: no plano gratuito do Render o disco é efêmero — o arquivo
`oz_store.db` (SQLite) é apagado a cada novo deploy/reinício. Para produção
de verdade, migre para Postgres (Render oferece um plano gratuito) ou use
um disco persistente pago.

## Estrutura

- `app.py` — rotas e lógica da loja e do painel admin
- `database.py` — schema SQLite + seed com dados reais do Discord
- `templates/` — todas as páginas (loja + admin)
- `static/` — CSS (tema escuro neon) e JS

## O que já funciona

- Loja com busca e filtro por categoria
- Página de produto com preço por faixa de quantidade (configurável no admin)
- Carrinho (adicionar/remover/atualizar quantidade)
- Checkout com geração de pedido + código Pix (placeholder — plugue seu
  gateway real substituindo `gen_pix_code` em `app.py`)
- Baixa automática de estoque a cada compra confirmada no checkout
- Minha conta / histórico de pedidos / avaliação pós-entrega
- Suporte (tickets), Pedir Stock, Parcerias, Regras, Avaliações
- Painel admin: dashboard, CRUD de produtos, faixas de preço, restock,
  gestão de pedidos (mudar status), tickets (responder/finalizar),
  pedidos de stock, parcerias, avaliações
