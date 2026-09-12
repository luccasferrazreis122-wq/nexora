# Backend NEXORA — publicação e operação

Esta pasta é um projeto independente do desktop. A API foi integrada ao FZ Optimizer,
mas precisa ser hospedada antes de funcionar em computadores de clientes.
Nunca copie OPENAI_API_KEY para o aplicativo, arquivos .spec, código-fonte ou executável.

## Publicação gratuita: Render Free + Neon Free

Esta versão 0.2 substitui o disco pago por PostgreSQL externo. É uma opção para testes
iniciais, sujeita às cotas dos dois serviços. O consumo da OpenAI continua pago.

1. Crie uma conta em https://neon.com no plano **Free**, e crie um projeto `nexora`.
2. No painel do Neon, abra **Connect** e copie a connection string PostgreSQL. Ela
   contém senha: não envie pelo chat nem coloque no GitHub. Use um banco exclusivo da NEXORA.
3. Atualize o repositório GitHub com o conteúdo extraído do ZIP atualizado
   `release/nexora-backend-publicacao.zip`. Substitua também `render.yaml`, `store.py`,
   `settings.py`, `admin.py`, `pyproject.toml` e `requirements.txt`. Não envie o ZIP fechado.
4. No Render, escolha **New > Web Service**, selecione o repositório `nexora` e configure:
   - Language/Runtime: **Python 3** (se detectar Docker, mude para Python).
   - Branch: `main`; Root Directory: deixe vazio.
   - Build Command: `pip install .`
   - Start Command: `uvicorn nexora_backend.api:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --no-proxy-headers --limit-concurrency 32`
   - Instance Type: **Free**. Não adicione disco, banco Render ou serviço pago.
5. Em Environment Variables configure:
   - `PYTHON_VERSION`: `3.12.12`
   - `OPENAI_API_KEY`: a chave diretamente no campo secreto do Render.
   - `DATABASE_URL`: a conexão PostgreSQL do Neon, no campo secreto do Render.
   - `NEXORA_REQUIRE_POSTGRES`: `1`
6. Publique. A rota `/health` deve retornar `{"status":"ok"}`. Esse teste não verifica
   saldo/modelo na OpenAI. O `render.yaml` também foi alterado para `plan: free`, sem disco,
   caso você prefira importar por Blueprint. Se pedirem cartão, não escolha plano pago
   para contornar: confira se o repositório já contém a configuração gratuita.
7. Emita um código pelo terminal local conforme a próxima seção, pois o Render Free
   não oferece Shell. Depois configure a URL HTTPS real no build do desktop.

O Render suspende serviços gratuitos após 15 minutos sem tráfego; a retomada pode levar
cerca de um minuto. O cliente aguarda até 120 segundos por requisição, sem repetir
chamadas pagas automaticamente. Não implemente pings para impedir a suspensão.
As cotas gratuitas podem suspender a API ou o banco: essa implantação não tem garantia
para distribuição pública em grande escala. O Render recomenda Free para testes,
não para produção. Não usamos o Postgres Free do Render, que expira após 30 dias.

As contas, sessões e cotas ficam no Neon e sobrevivem a reinícios do Render. O backend
recusa inicializar na configuração Free sem DATABASE_URL PostgreSQL. A conexão valida
certificado e hostname com TLS. A URL do banco nunca vai para o executável.

Referências oficiais consultadas:
- https://render.com/docs/free
- https://neon.com/pricing
- https://neon.com/blog/how-to-make-the-most-of-neons-free-plan
- https://developers.openai.com/api/reference/overview#authentication

## Operação pelo terminal local do administrador

Dentro de `fz_optimizer`, instale as dependências do backend no ambiente virtual.
Execute no seu PowerShell (não no computador dos clientes):

```powershell
.\.venv-nexora\Scripts\python.exe -m nexora_backend.admin --database-prompt create --label cliente-001 --days 7
.\.venv-nexora\Scripts\python.exe -m nexora_backend.admin --database-prompt list
.\.venv-nexora\Scripts\python.exe -m nexora_backend.admin --database-prompt extend ID_DO_USUARIO --days 30
.\.venv-nexora\Scripts\python.exe -m nexora_backend.admin --database-prompt revoke ID_DO_USUARIO
.\.venv-nexora\Scripts\python.exe -m nexora_backend.admin --database-prompt reissue ID_DO_USUARIO
```

O comando solicita a conexão do Neon em um campo oculto, sem colocá-la no histórico
do terminal ou em arquivo. O código de ativação retornado é individual; entregue-o
somente ao cliente correspondente. Nenhuma chave OpenAI é necessária para administrar.
Faça backups PostgreSQL com `pg_dump` ou as ferramentas do provedor, protegendo a cópia.
O comando `backup` do utilitário atende somente SQLite local.

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
- Faça backup do banco e transfira uma cópia para armazenamento separado.
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
  acesso à conexão PostgreSQL no terminal do administrador. Proteja as contas dos provedores com autenticação em duas etapas.
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
- PostgreSQL compartilha cotas e revogações entre instâncias. Um lock transacional
  serializa operações curtas de autorização para evitar ultrapassar cotas simultaneamente;
  ele é liberado antes da chamada OpenAI. SQLite permanece disponível apenas como opção
  local ou com disco persistente; não use SQLite no plano gratuito.
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
# Atualização 0.3: teste automático de 7 dias

O aplicativo registra uma credencial aleatória individual em `POST /v1/auth/trial` ao abrir
a página NEXORA pela primeira vez. Não pede código. O banco fixa a expiração em 7 dias
(168 horas) segundo o relógio do servidor. Reconexões recuperam o mesmo usuário e prazo.
O desktop salva a credencial com Windows DPAPI antes da requisição; o servidor guarda
somente seu hash. A chave OpenAI continua exclusivamente no Render.

Configurações opcionais (os padrões já funcionam):
- `NEXORA_TRIALS_ENABLED=1`: use `0` para interromper novos cadastros, preservando existentes.
- `NEXORA_TRIAL_DAILY_REGISTRATIONS=20`: novos testes por dia UTC no serviço inteiro.
- `NEXORA_TRIAL_PEER_DAILY_REGISTRATIONS=3`: novos testes por origem de conexão/dia UTC.
- Permanecem as cotas de chat: 30 pedidos/usuário/dia, 300 globais/dia, 5/usuário/minuto,
  30 globais/minuto e saída limitada a 650 tokens por pedido.

O peer é o endereço observado pelo servidor, sem confiar em X-Forwarded-For enviado
pelo cliente. No Render ele pode ser um proxy compartilhado, então o limite por peer
pode atingir usuários diferentes. Esses limites não garantem identidade por pessoa:
apagar os dados locais ou criar outra identidade pode gerar outro teste. Para impedir
isso de forma mais forte será necessário cadastro verificado. As cotas globais limitam
as chamadas mesmo assim; não são um orçamento monetário exato.

Contas manuais existentes mantêm seus prazos. `admin extend` renova o usuário automático;
`admin revoke` bloqueia inclusive a recuperação pela credencial de instalação. Reemitir
um código não revoga a credencial de instalação; use revoke para bloquear o usuário.
O botão **Usar código** continua disponível para acessos fornecidos pelo administrador.

Publicação: envie os arquivos do ZIP atualizado ao mesmo repositório no GitHub e aguarde
o deploy no Render. O banco recebe somente a nova tabela `installations`, sem apagar
contas existentes. Publique o novo executável depois do deploy do backend.
