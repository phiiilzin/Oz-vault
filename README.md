# Oz Vault Store

Loja online completa para o servidor Discord **Oz Vault** (Grow a Garden 2), construída em **Flask + SQLite**, com a estrutura de navegação inspirada na MYU Store e identidade visual própria (tema escuro neon rosa/roxo, estilo "cofre mágico").

## Como rodar

```bash
cd ozvault
pip install -r requirements.txt
python3 app.py
```

O site sobe em `http://localhost:5000`. O banco de dados SQLite (`ozvault.db`) é criado automaticamente na primeira execução, já populado com as categorias e produtos (Seeds, Regadores, Maple, Sheckles, Sem Mínimo).

## Login de administrador padrão

- **Usuário:** `admin`
- **Senha:** `ozvault-admin`

⚠️ **Troque essa senha antes de usar em produção** (crie um novo admin pelo painel do banco ou registre um usuário e promova-o manualmente com `UPDATE users SET is_admin = 1 WHERE username = '...'`).

## O que está implementado

- **Loja pública:** Home, Loja (busca + filtros por categoria), Estoque em tempo real, página de produto com preço por faixa de quantidade.
- **Carrinho e checkout:** preços e estoque sempre recalculados no servidor (nunca confia em valores vindos do navegador); geração de pedido com código PIX "copia e cola" (placeholder — a confirmação real de pagamento deve vir de um webhook do seu provedor de pagamento).
- **Conta de usuário:** cadastro/login com senha em hash, histórico de pedidos, avaliação de pedidos entregues.
- **Suporte:** sistema de tickets (Comprar estoque / Suporte / Parceria / Outro) com chat entre cliente e equipe.
- **Pedir Stock:** formulário para o cliente solicitar novos produtos.
- **Restock:** lista de produtos que voltaram ao estoque + botão "avisar quando voltar".
- **Avaliações:** só é possível avaliar após um pedido marcado como "entregue".
- **Parcerias e Regras:** páginas dedicadas.
- **Painel administrativo (`/admin`):** dashboard com métricas, CRUD de produtos (preço, estoque, categoria, imagem, faixas de preço por quantidade, ativar/desativar), gestão de pedidos (mudar status), tickets (responder/finalizar), avaliações, pedidos de estoque e parcerias.
- **Mobile-first:** navbar vira menu hambúrguer, tabbar fixa inferior, tabelas viram cards no celular (sem scroll horizontal), botões grandes.

## Estrutura do banco (SQLite, criado automaticamente)

`users`, `categories`, `products`, `price_tiers`, `orders`, `order_items`, `payments`, `tickets`, `ticket_messages`, `reviews`, `stock_requests`, `restocks`, `partnerships`, `notifications`, `restock_alerts`.

## Próximos passos sugeridos (não implementados por serem integrações externas)

- Integração real com um provedor de PIX (ex. Mercado Pago, Efí, Gerencianet) para confirmar pagamentos automaticamente via webhook.
- Bot de Discord para notificar a equipe sobre novos tickets/pedidos de estoque/parcerias.
- Envio de e-mail/Discord DM para os alertas de restock (`restock_alerts`).
