/**
 * Mad-planlægning — Google Sheets API for Home Assistant  (2026-07-29)
 * ---------------------------------------------------------------------------
 * Indsættes i selve ret-arket:  Udvidelser → Apps Script → erstat al kode med
 * denne fil → Gem → Udrul → Ny udrulning → type "Webapp":
 *     Kør som:        Mig (din egen konto)
 *     Hvem har adgang: Alle          ← krævet, HA kan ikke logge ind
 * → kopiér web-app-URL'en (…/exec) og giv den til Claude.
 *
 * SIKKERHED: URL'en er offentlig, så alle kald kræver ?token=<TOKEN> nedenfor.
 * Skift TOKEN til en tilfældig streng FØR du udruller. Uden korrekt token
 * svarer scriptet 403 og rører ikke arket.
 *
 * ⚠️ GENUDRULNING: denne fil ligger i git, så dens TOKEN er OFFENTLIG. Indsætter
 * du hele filen igen, overskriver du din egen token med placeholderen — og så
 * kan hvem som helst med URL'en skrive i arket. Bevar linjen `var TOKEN = …`,
 * eller sæt den igen bagefter. Scriptet nægter at svare mens placeholderen står.
 *
 * ALT er GET-baseret med vilje: Apps Script svarer 302 på POST, og de fleste
 * HTTP-klienter (urllib/requests/aiohttp) smider POST-body'en væk i det redirect.
 *
 * Endpoints (alle: ?token=…&action=…):
 *   ping                                  → {ok, sheet, rows}
 *   setup                                 → opretter manglende kolonner + ID'er
 *   dishes                                → alle retter som JSON
 *   vote    &id=12&person=parent_a&svar=JA  → skriver stemme (JA/NIX/MAASKE/"")
 *   asked   &ids=12,15[&dato=2026-08-01]  → stempler "Sidst spurgt" (uden
 *                                           dato: i dag)
 *   struct  &id=12&value=500|g|hakket oksekød;2|stk|løg
 *   add     &ret=…&kategori=…&bv=Ja&sv=Let&ing=…&guide=…&struct=…
 * ---------------------------------------------------------------------------
 */

var TOKEN = 'SKIFT-MIG-TIL-EN-TILFAELDIG-STRENG';
var TOKEN_PLACEHOLDER = 'SKIFT-MIG-TIL-EN-TILFAELDIG-STRENG';

// Kolonne-overskrifter. De 6 første SKAL matche arket som det ser ud i dag.
var H_ID      = 'ID';
var H_RET     = 'Ret';
var H_KAT     = 'Kategori';
var H_BV      = 'Børnevenlig';
var H_SV      = 'Sværhedsgrad';
var H_ING     = 'Ingredienser';
var H_GUIDE   = 'Trin-for-trin Guide';
var H_STRUCT  = 'Ingredienser_struktureret';
var H_PARENT_A  = 'Parent A';
var H_PARENT_B = 'Parent B';
var H_SPURGT  = 'Sidst spurgt';
// 2026-08-05: user tilføjede fire kolonner i hånden (L-O). De LÆSES kun og står
// bevidst IKKE i NEW_COLS — mangler de, giver cell() tom streng, og
// mad_planner.py fejler åbent (tom sæson = altid i sæson).
var H_MADKAT  = 'Mad kategori';
var H_SUNDHED = 'Sundhed';
var H_TID     = 'Tilberedningstid (minutter)';
var H_SAESON  = 'Sæson';

// Kolonner der oprettes hvis de mangler (i denne rækkefølge, bagerst i arket).
var NEW_COLS = [H_ID, H_STRUCT, H_PARENT_A, H_PARENT_B, H_SPURGT];

var VALID_VOTES = ['JA', 'NIX', 'MAASKE', ''];


function doGet(e) {
  var p = (e && e.parameter) || {};
  // Fejl LUKKET på placeholderen: den står i git, så ville den virke, var arket
  // åbent for alle der kender URL'en. 2026-08-05 blev hele filen genindsat og
  // tog placeholderen med — den skal give en tydelig fejl, ikke stille adgang.
  if (TOKEN === TOKEN_PLACEHOLDER) {
    return out({ ok: false, error: 'TOKEN er ikke sat — ret var TOKEN i Apps Script og udrul igen' });
  }
  if (p.token !== TOKEN) return out({ ok: false, error: 'bad token' });

  try {
    switch (p.action) {
      case 'ping':   return out(apiPing());
      case 'setup':  return out(apiSetup());
      case 'dishes': return out(apiDishes());
      case 'vote':   return out(apiVote(p.id, p.person, p.svar, p.ret));
      case 'asked':  return out(apiAsked(p.ids, p.dato));
      case 'struct': return out(apiStruct(p.id, p.value));
      case 'add':    return out(apiAdd(p));
      default:       return out({ ok: false, error: 'unknown action: ' + p.action });
    }
  } catch (err) {
    return out({ ok: false, error: String(err) });
  }
}

// doPost peger på samme handler, så et evt. POST-kald også virker.
function doPost(e) { return doGet(e); }


/* -------------------------------------------------------------------------- */
/* Hjælpere                                                                    */
/* -------------------------------------------------------------------------- */

function out(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function sheet() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
}

/** {header: 1-baseret kolonneindeks} */
function headerMap(sh) {
  var lastCol = Math.max(sh.getLastColumn(), 1);
  var head = sh.getRange(1, 1, 1, lastCol).getValues()[0];
  var map = {};
  for (var i = 0; i < head.length; i++) {
    var name = String(head[i]).trim();
    if (name) map[name] = i + 1;
  }
  return map;
}

/** Sikrer at alle NEW_COLS findes + at alle rækker har et unikt ID. */
function apiSetup() {
  var sh = sheet();
  var map = headerMap(sh);
  var added = [];

  NEW_COLS.forEach(function (name) {
    if (!map[name]) {
      var col = sh.getLastColumn() + 1;
      sh.getRange(1, col).setValue(name);
      map[name] = col;
      added.push(name);
    }
  });

  // Tildel ID til rækker der mangler et (bevarer eksisterende ID'er).
  var last = sh.getLastRow();
  var assigned = 0;
  if (last > 1) {
    var idCol = map[H_ID];
    var ids = sh.getRange(2, idCol, last - 1, 1).getValues();
    var maxId = 0;
    ids.forEach(function (r) {
      var v = parseInt(r[0], 10);
      if (!isNaN(v) && v > maxId) maxId = v;
    });
    for (var i = 0; i < ids.length; i++) {
      if (String(ids[i][0]).trim() === '') {
        ids[i][0] = ++maxId;
        assigned++;
      }
    }
    sh.getRange(2, idCol, last - 1, 1).setValues(ids);
  }

  sh.setFrozenRows(1);
  return { ok: true, added: added, ids_assigned: assigned, rows: Math.max(last - 1, 0) };
}

function apiPing() {
  var sh = sheet();
  return {
    ok: true,
    sheet: sh.getName(),
    rows: Math.max(sh.getLastRow() - 1, 0),
    columns: Object.keys(headerMap(sh))
  };
}

function rowsWithIds(sh, map) {
  var last = sh.getLastRow();
  if (last < 2 || !map[H_ID]) return {};
  var ids = sh.getRange(2, map[H_ID], last - 1, 1).getValues();
  var byId = {};
  for (var i = 0; i < ids.length; i++) {
    var v = String(ids[i][0]).trim();
    if (v) byId[v] = i + 2;   // arkets rækkenummer
  }
  return byId;
}

function cell(row, map, header) {
  if (!map[header]) return '';
  var v = row[map[header] - 1];
  // Sheets auto-konverterer 'ÅÅÅÅ-MM-DD' til en ægte dato-celle; uden denne
  // formatering ville den blive læst som "Wed Jul 29 2026 00:00:00 GMT+0200".
  // (mad_planner.py::parse_dato tåler begge former — dette er kosmetik.)
  if (Object.prototype.toString.call(v) === '[object Date]') {
    return Utilities.formatDate(v, 'Europe/Copenhagen', 'yyyy-MM-dd');
  }
  return String(v).trim();
}


/* -------------------------------------------------------------------------- */
/* Læsning                                                                     */
/* -------------------------------------------------------------------------- */

function apiDishes() {
  var sh = sheet();
  var map = headerMap(sh);
  var last = sh.getLastRow();
  if (last < 2) return { ok: true, dishes: [] };

  var values = sh.getRange(2, 1, last - 1, sh.getLastColumn()).getValues();
  var dishes = [];

  for (var i = 0; i < values.length; i++) {
    var r = values[i];
    var name = cell(r, map, H_RET);
    if (!name) continue;
    dishes.push({
      id: cell(r, map, H_ID),
      row: i + 2,
      ret: name,
      kategori: cell(r, map, H_KAT),
      boernevenlig: cell(r, map, H_BV),
      svaerhedsgrad: cell(r, map, H_SV),
      ingredienser: cell(r, map, H_ING),
      guide: cell(r, map, H_GUIDE),
      struct: cell(r, map, H_STRUCT),
      parent_a: cell(r, map, H_PARENT_A).toUpperCase(),
      parent_b: cell(r, map, H_PARENT_B).toUpperCase(),
      spurgt: cell(r, map, H_SPURGT),
      mad_kategori: cell(r, map, H_MADKAT),
      sundhed: cell(r, map, H_SUNDHED),
      tilberedningstid: cell(r, map, H_TID),
      saeson: cell(r, map, H_SAESON)
    });
  }
  return { ok: true, dishes: dishes, count: dishes.length };
}


/* -------------------------------------------------------------------------- */
/* Skrivning                                                                   */
/* -------------------------------------------------------------------------- */

function apiVote(id, person, svar, ret) {
  var sh = sheet();
  var map = headerMap(sh);
  var byId = rowsWithIds(sh, map);
  var row = byId[String(id).trim()];
  if (!row) return { ok: false, error: 'ukendt id: ' + id };

  // ID-kolonnen er POSITIONEL: indsættes/slettes en række, forskydes alle id'er
  // under den, og en stemme skrevet under et gammelt id lander på naboretten.
  // Sender kalderen rettens NAVN med, verificeres det før vi skriver — sidste
  // spærring mod usynlig forurening af puljen. Uden 'ret' (gamle kald) skrives
  // som før.
  if (ret && map[H_RET]) {
    var faktisk = String(sh.getRange(row, map[H_RET]).getValue() || '').trim();
    if (faktisk !== String(ret).trim()) {
      return { ok: false, error: 'id ' + id + ' er "' + faktisk +
                                 '", ikke "' + ret + '"' };
    }
  }

  var p = String(person || '').toLowerCase();
  var col = p === 'parent_a' ? map[H_PARENT_A] : (p === 'parent_b' ? map[H_PARENT_B] : null);
  if (!col) return { ok: false, error: 'ukendt person: ' + person };

  var v = String(svar || '').toUpperCase();
  if (VALID_VOTES.indexOf(v) === -1) return { ok: false, error: 'ugyldigt svar: ' + svar };

  sh.getRange(row, col).setValue(v);
  return { ok: true, id: id, person: p, svar: v, row: row };
}

function apiAsked(ids, dato) {
  var sh = sheet();
  var map = headerMap(sh);
  if (!map[H_SPURGT]) return { ok: false, error: 'kolonne mangler: ' + H_SPURGT };
  var byId = rowsWithIds(sh, map);
  // Uden 'dato' stemples i dag — det er det rigtige når vi lige HAR spurgt.
  // En genopbygning fra lokal state skal derimod kunne skrive den ÆGTE dato:
  // 2026-08-05 fladede en synk hele spørge-historikken ud til én dag, hvilket
  // både gjorde "seneste svar" statisk og nulstillede genspørg-intervallet.
  var stempel = /^\d{4}-\d{2}-\d{2}$/.test(String(dato || '').trim())
    ? String(dato).trim()
    : Utilities.formatDate(new Date(), 'Europe/Copenhagen', 'yyyy-MM-dd');
  var done = [];
  String(ids || '').split(',').forEach(function (raw) {
    var id = raw.trim();
    if (!id || !byId[id]) return;
    sh.getRange(byId[id], map[H_SPURGT]).setValue(stempel);
    done.push(id);
  });
  return { ok: true, stamped: done, dato: stempel };
}

function apiStruct(id, value) {
  var sh = sheet();
  var map = headerMap(sh);
  if (!map[H_STRUCT]) return { ok: false, error: 'kolonne mangler: ' + H_STRUCT };
  var byId = rowsWithIds(sh, map);
  var row = byId[String(id).trim()];
  if (!row) return { ok: false, error: 'ukendt id: ' + id };
  sh.getRange(row, map[H_STRUCT]).setValue(String(value || ''));
  return { ok: true, id: id, row: row };
}

function apiAdd(p) {
  var sh = sheet();
  var map = headerMap(sh);
  if (!p.ret) return { ok: false, error: 'ret mangler' };

  // Næste ID
  var byId = rowsWithIds(sh, map);
  var maxId = 0;
  Object.keys(byId).forEach(function (k) {
    var v = parseInt(k, 10);
    if (!isNaN(v) && v > maxId) maxId = v;
  });

  var row = new Array(sh.getLastColumn());
  for (var i = 0; i < row.length; i++) row[i] = '';
  function put(header, value) {
    if (map[header]) row[map[header] - 1] = value == null ? '' : value;
  }
  put(H_ID, maxId + 1);
  put(H_RET, p.ret);
  put(H_KAT, p.kategori || 'Aftensmad');
  put(H_BV, p.bv || '');
  put(H_SV, p.sv || '');
  put(H_ING, p.ing || '');
  put(H_GUIDE, p.guide || '');
  put(H_STRUCT, p.struct || '');

  sh.appendRow(row);
  return { ok: true, id: maxId + 1, ret: p.ret };
}
