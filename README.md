# Prima installazione RTU Areti - Dante Smart HUB

Applicazione Python locale con interfaccia web integrata, destinata alla prima
installazione delle RTU Areti e alla loro attestazione alla piattaforma
**Dante Smart HUB**.

## Stato dello scheletro

Sono predisposti due servizi backend e le relative sezioni web:

1. **Attestazione**: connessione SSH tramite Paramiko, confronto della versione
   RTU con una versione fissa, trasferimento di uno script `.sh` tramite SCP ed
   esecuzione remota. Al primo errore il flusso si interrompe e i passi successivi
   risultano `NON_ESEGUITO`.
2. **Verifica attestazione**: sequenza estendibile di controlli indipendenti,
   report per ogni test ed esito finale. Un KO non interrompe gli altri controlli.

Non sono ancora disponibili credenziali, comando di lettura versione, versione
compatibile, script reale e specifiche dei controlli. **Non viene simulata
un'attestazione riuscita**: senza prerequisiti la procedura restituisce
`NON_CONFIGURATO` e non si collega alla RTU. I due controlli iniziali di verifica
sono segnaposto, non implementazioni della comunicazione REST o della piattaforma.

## Avvio

Prerequisiti: Python 3.10 o successivo, ambiente grafico e connettivita' verso la
RTU. Su Linux il frontend usa Qt; su Windows usa il backend di pywebview disponibile.

```sh
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python app.py
```

Su Windows usare `venv\Scripts\python.exe` al posto di `venv/bin/python`.
Su Linux sono disponibili anche `make install`, `make run` e `make test`.

Nella pagina inserire l'indirizzo IPv4 o IPv6 della RTU, quindi avviare
l'attestazione o la verifica. Gli hostname non sono accettati. Durante
un'operazione i pulsanti e l'indirizzo sono bloccati: non vengono eseguite
operazioni concorrenti nella stessa istanza.

## Architettura e contratto dei servizi

La pagina usa il bridge locale `window.pywebview.api`: non viene avviato un
server HTTP e non vengono esposte API sulla rete.

| Chiamata dalla pagina | Servizio Python | Funzione |
|---|---|---|
| `attest_rtu(ip)` | `AttestationService.attest` | Prima configurazione via SSH/SCP |
| `verify_attestation(ip)` | `VerificationService.verify` | Report dei controlli di attestazione |

Entrambe restituiscono un oggetto serializzabile:

```json
{
  "operation": "verifica",
  "ip": "192.168.1.10",
  "status": "NON_CONFIGURATO",
  "message": "Verifica incompleta: definire e implementare tutti i controlli.",
  "tests": [
    {
      "name": "Comunicazione REST",
      "status": "NON_CONFIGURATO",
      "detail": "Controllo non ancora implementato."
    },
    {
      "name": "Controllo attestazione Dante Smart HUB (da definire)",
      "status": "NON_CONFIGURATO",
      "detail": "Controllo non ancora implementato."
    }
  ]
}
```

Il frontend mostra `Test 1: Comunicazione REST - OK/KO/...`, il dettaglio di
ogni test e l'esito finale. Stati: `OK`, `KO`, `NON_CONFIGURATO`,
`NON_ESEGUITO` (solo passi di attestazione saltati).
La verifica e' OK solo se esiste almeno un controllo e **tutti** sono OK;
un KO prevale sui controlli non configurati.

## Completare l'attestazione SSH/SCP

In `device/settings.py` impostare i valori fissi, dopo averli concordati con
chi gestisce le RTU:

| Impostazione | Significato |
|---|---|
| `EXPECTED_VERSION` | Versione RTU ammessa, inizialmente vuota |
| `VERSION_COMMAND` | Comando remoto di lettura versione, inizialmente vuoto |
| `LOCAL_SCRIPT` | Script locale, predefinito `scripts/attest_rtu.sh` |
| `REMOTE_SCRIPT` | Destinazione sulla RTU, predefinita `/tmp/areti-attestazione.sh` |
| `SSH_PORT` | Porta SSH, predefinita 22 |
| `SSH_TIMEOUT` | Timeout connessione/autenticazione/trasferimento, 10 secondi |
| `COMMAND_TIMEOUT` | Limite per ciascun comando remoto, 120 secondi |

Il comando di versione deve terminare con exit code 0 e stampare su stdout
soltanto la versione. Il confronto e' esatto dopo la rimozione degli spazi
iniziali/finali: una versione diversa impedisce trasferimento ed esecuzione.

Fornire lo script reale in `scripts/attest_rtu.sh` (non incluso nello scheletro).
Deve essere compatibile con `sh`, eseguibile senza interazione e restituire 0
solo quando la procedura e' riuscita. Non viene richiesta una shell interattiva,
un PTY o `sudo`. La destinazione deve essere scrivibile dall'utente SSH e lo
script rimane sul dispositivo; confermare percorso, permessi, idempotenza e
politica di pulizia prima dell'uso operativo. Non avviare altre istanze sullo
stesso dispositivo durante la procedura.

Le credenziali fisse vengono definite **nel codice Python locale**, senza
commetterle nel repository: creare `local_settings.py` nella root del progetto,
gia' escluso da Git, con le costanti `SSH_USERNAME` e `SSH_PASSWORD`.
Il file e' caricato come codice Python: mantenerlo sotto controllo
dell'operatore e proteggerne i permessi. Le credenziali non sono richieste o
trasmesse dalla pagina e non vengono inserite nel report.

Paramiko rifiuta chiavi host sconosciute o diverse da quelle note. Prima di
collegarsi, registrare la chiave della RTU nel `known_hosts` dell'utente locale
dopo aver verificato il fingerprint tramite un canale affidabile. Non viene
abilitata l'accettazione automatica delle chiavi.

Il report di attestazione OK certifica soltanto l'exit code 0 dello script:
**non prova da solo l'avvenuta attestazione a Dante Smart HUB**. Eseguire poi
la verifica. In caso di timeout o perdita della connessione durante lo script,
lo stato remoto puo' essere incerto: controllare la RTU prima di riprovare.
Stdout/stderr remoti non vengono mostrati nella pagina; gli errori di rete e
autenticazione producono un KO e una segnalazione nei log locali.

## Completare i controlli di verifica

In `device/attestation.py`, sostituire/estendere la sequenza
`VerificationService.checks` con i controlli reali. Ogni `VerificationCheck`
ha una descrizione e una funzione `run(ip)` che restituisce un `CheckResult`
con `name`, `status` e `detail`. Una funzione assente produce
`NON_CONFIGURATO`. Sono ammessi `OK`, `KO`, `NON_CONFIGURATO`.

Prima di implementarli vanno definiti numero e ordine dei test, endpoint REST,
protocollo e autenticazione, timeout, dati necessari e criteri di successo.
Le funzioni devono impostare timeout sulle chiamate di rete e tradurre gli
errori specifici del protocollo in un KO con dettaglio comprensibile, evitando
di includere segreti o risposte remote sensibili.

## File principali

| File | Responsabilita' |
|---|---|
| `app.py` | Finestra pywebview, validazione IP e bridge ai due servizi |
| `device/attestation.py` | Flusso SSH/SCP, sequenza di verifiche e report |
| `device/settings.py` | Parametri fissi e caricamento credenziali locali |
| `ui/` | Pagina, pulsanti, stato operazioni e report |
| `test/test_attestation.py` | Test automatici senza RTU reale |

`device/device_client.py` e `test/device_stub.py` appartengono al precedente
prototipo REST generico: non sono usati dai nuovi flussi e non simulano
Dante Smart HUB.

## Distribuzione

`make build` genera l'eseguibile con PyInstaller includendo la UI e, se
disponibile, `scripts/attest_rtu.sh`. Per includere lo script occorre quindi
fornirlo **prima** della build. Le costanti in `device/settings.py` vengono
incorporate nella build e richiedono una nuova build quando cambiano.

Le credenziali non vengono incorporate: affiancare `local_settings.py`
all'eseguibile distribuito, proteggendone accesso e permessi. Anche nell'uso
distribuito sono necessarie le chiavi host note dell'operatore.

Per eseguire i test senza connessioni reali:

```sh
venv/bin/python -m unittest discover -s test -p 'test_*.py'
```
