# Backend NEXORA — publicação e operação

Esta pasta é um projeto independente do desktop. A API foi integrada ao FZ Optimizer,
mas precisa ser hospedada antes de funcionar em computadores de clientes.
Nunca copie OPENAI_API_KEY para o aplicativo, arquivos .spec, código-fonte ou executável.

## Caminho recomendado para quem não tem VPS

1. Crie sua conta em https://render.com e uma conta no GitHub, se ainda não tiver.
2. Crie um repositório privado `nexora-backend`. Envie **o conteúdo desta pasta** para a
   raiz dele (README, arquivos Python, pyproject.toml, requirements, render.yaml etc.).
   Não envie a pasta inteira do FZ Optimizer, `.env`, bancos, sessões, logs ou ambientes virtuais.
   O arquivo `release/nexora-backend-publicacao.zip`, gerado na entrega, já contém somente
   os arquivos necessários. Extraia seu conteúdo para o repositório, incluindo os arquivos ocultos.
3. No Render, escolha **New > Blueprint**, conecte esse repositório e revise o serviço
   descrito em `render.yaml`. Ele usa Python, plano Starter e disco persistente de 1 GB.
   Confira o preço no painel antes de contratar. API OpenAI e hospedagem são cobradas separadamente.
4. No campo secreto `OPENAI_API_KEY`, configure a chave diretamente no painel do Render.
   Não coloque esse valor no GitHub nem no chat. A aplicação falha na inicialização se faltar a chave.
5. Confirme que `NEXORA_DATABASE=/var/data/nexora.sqlite3` e que o disco está montado
   em `/var/data`. Sem persistência, reinícios perderiam usuários, sessões e cotas.
6. Após publicar, abra `https://SEU-SERVICO.onrender.com/health`. A resposta esperada é
   `{"status":"ok"}`. Esse teste não chama a OpenAI nem comprova que há saldo/acesso ao modelo.
7. Abra **Shell** no serviço e execute `nexora-admin create --label teste-interno --days 7`.
   Guarde o `user_id` e entregue o `activation_code` somente ao usuário correspondente.
8. Configure a URL pública no build desktop conforme o guia `NEXORA_IMPLEMENTACAO.md`.
   Clique em **Ativar NEXORA**, informe o código e envie uma mensagem curta.
   Esse último teste já chama a OpenAI e consome créditos.

O subdomínio `onrender.com` evita comprar um domínio próprio agora. O HTTPS é provido
pela hospedagem. O Render exige serviço pago para disco persistente; não utilize um
serviço gratuito efêmero com este SQLite.

Referências oficiais:
- https://render.com/docs/deploy-fastapi
- https://render.com/docs/disks
- https://render.com/docs/blueprint-spec
- https://developers.openai.com/api/reference/overview#authentication

## Operação pelo terminal do servidor

```sh
nexora-admin create --label cliente-001 --days 7
nexora-admin list
nexora-admin extend ID_DO_USUARIO --days 30
nexora-admin revoke ID_DO_USUARIO
nexora-admin reissue ID_DO_USUARIO
nexora-admin backup /var/data/nexora-backup.sqlite3
```

- A ativação pode ser resgatada uma única vez, até 7 dias após emissão.
- O prazo de acesso começa no primeiro resgate, usando o relógio do servidor.
- Access token: até 15 minutos. Refresh token: até 30 dias ou o vencimento do acesso.
- Refresh é rotativo: o token anterior e os access tokens anteriores são invalidados.
- `reissue` invalida as sessões existentes e emite outro código sem reiniciar o prazo.
  Após `revoke`, primeiro use `extend` para liberar o acesso e depois `reissue`.
- Esta primeira versão usa liberação manual. Não há cadastro público, envio de e-mail,
  pagamento automático, recuperação de senha ou emissão anônima ilimitada de testes.
- Uma conta possui uma sessão renovável. Compartilhar a conta entre várias instalações
  pode invalidar sessões. Em caso de perda da resposta de ativação/refresh, use `reissue`.
- O banco guarda hashes dos tokens, nunca seus valores originais. Identificações internas
  e datas de acesso ficam no banco; evite usar dados pessoais desnecessários no label.
- Faça backup pelo comando acima e transfira uma cópia para armazenamento separado.
  Teste restauração com o serviço parado. Uma restauração antiga também restaura cotas
  e revogações antigas: revise os acessos antes de reabrir o serviço.

## Limites iniciais

| Variável | Padrão |
| --- | --- |
| NEXORA_USER_DAILY_REQUESTS | 30 |
| NEXORA_GLOBAL_DAILY_REQUESTS | 300 |
| NEXORA_USER_MINUTE_REQUESTS | 5 |
| NEXORA_GLOBAL_MINUTE_REQUESTS | 30 |
| NEXORA_MODEL | gpt-5.4-mini |

Os limites são cobrados atomicamente **antes** da chamada ao provedor, inclusive quando
o provedor falha. Dias viram à meia-noite UTC; minutos são janelas fixas.
Autenticação tem limite adicional de 10 tentativas/minuto por peer e 100 globalmente.
Não confiamos em X-Forwarded-For enviado pelo cliente. Atrás do proxy do Render, vários
usuários podem compartilhar o mesmo peer; monitore esse limite antes de aumentar o público.

Cada chamada aceita no máximo 4.000 caracteres na mensagem, 12 mensagens no histórico,
16.000 bytes UTF-8 no texto total recebido e 650 tokens de saída. O corpo HTTP também
tem limite. Essas barreiras limitam consumo, mas **não são um orçamento monetário exato**.
Configure alertas/limites também no projeto OpenAI e acompanhe o consumo real.
Não há retry automático de chamadas pagas; falhas de rede não geram novas cobranças por repetição no cliente.

O modelo atual foi preservado, não validado com sua conta. Se a conta não tiver acesso,
configure `NEXORA_MODEL` no servidor para um modelo Responses disponível e teste a compatibilidade.

## Segurança, dados e disponibilidade

- Rotas: `/health`, `/v1/auth/activate`, `/v1/auth/refresh`, `/v1/me/access`, `/v1/nexora/chat`.
- Sem endpoint administrativo e sem segredo mestre no desktop. A administração exige
  acesso ao terminal da hospedagem. Proteja essa conta com autenticação em duas etapas.
- Prompt, modelo, limite de saída e destino OpenAI são controlados no servidor. Não há
  proxy genérico, execução remota de comandos ou ferramentas entregues ao modelo.
- As respostas da IA são texto. Confirmações e ações Windows continuam exclusivamente locais.
- Logs não incluem corpo das conversas, tokens, cabeçalhos de autorização ou exceções
  completas do provedor. IDs de requisição ajudam no diagnóstico. Revise também logs do proxy.
- O servidor usa `store=False` nas Responses. Isso não significa ausência de toda retenção
  pela OpenAI; observe as políticas da conta/provedor e informe o tratamento aos usuários.
- O desktop não envia automaticamente relatórios, nomes do computador nem caminhos locais.
  O histórico de chat vive na memória do aplicativo. Contexto explícito é tratado como dado
  de usuário, não como instrução privilegiada.
- SQLite foi escolhido para uma instância pequena com disco persistente. Não escale
  para múltiplas máquinas com bancos independentes: cotas e revogações deixariam de ser globais.
  Para esse crescimento, migrar Store para PostgreSQL e limites distribuídos é necessário.
- Configure monitoração externa de `/health` e alertas de erro/consumo na hospedagem.

## Execução local

A partir da pasta `fz_optimizer`:

```powershell
py -m venv .venv-nexora
.\.venv-nexora\Scripts\python.exe -m pip install -r nexora_backend/requirements-dev.txt
.\.venv-nexora\Scripts\python.exe -m pytest tests -q
```

Os testes injetam um provedor simulado: não usam chave nem gastam créditos. Para execução
real local, disponibilize a chave somente ao processo do backend por mecanismo seguro,
e rode `python -m uvicorn nexora_backend.api:create_app --factory --host 127.0.0.1 --port 8000`.
Não exponha essa porta sem HTTPS na internet. O cliente de produção aceita somente HTTPS;
HTTP local requer parâmetro explícito usado nos testes.

O Dockerfile é uma alternativa ao runtime Python. Nesse caso, use esta pasta como contexto
do build e monte um volume persistente em `/var/data`, gravável pelo UID 10001. Não inclua
segredos como build arguments ou arquivos da imagem.
