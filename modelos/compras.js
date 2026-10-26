(function () {
  // Busca nas licitações e nos contratos. O resumo e as últimas publicações já vêm prontos
  // na página; este script só carrega a base completa e filtra no próprio aparelho.
  var POR_PAGINA = 30;
  var moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  var D = null;
  var estado = { lic: 1, con: 1, emp: 1 };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = txt;
    return e;
  }
  function data(d) { return d ? d.split('-').reverse().join('/') : ''; }
  function sem(s) { return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function rotulo(pai, texto, valor) {
    var s = el('span');
    s.appendChild(document.createTextNode(texto + ': '));
    s.appendChild(el('b', null, valor));
    pai.appendChild(s);
  }
  function chip(sit) {
    var ok = sit === 'Concluída' || sit === 'Contratação direta publicada';
    var ruim = sit === 'Revogada' || sit === 'Deserta' || sit === 'Fracassada';
    return el('span', 'chip ' + (ok ? 'ok' : ruim ? 'falta' : 'info'), sit);
  }
  function link(base, sufixo, texto) {
    var a = el('a', null, texto);
    a.href = base + sufixo;
    a.rel = 'noopener';
    return a;
  }

  function cnpjFmt(k) { return k.slice(0, 2) + '.' + k.slice(2, 5) + '.' + k.slice(5, 8) + '/' + k.slice(8, 12) + '-' + k.slice(12); }

  // Empresa: [razão social, situação, data da situação, abertura, atividade, porte, cidade/UF, MEI, sócios, total contratado, nº de contratos]
  function quadroEmpresa(k, pai) {
    var e = D.emp[k];
    var meta = el('p', 'meta');
    rotulo(meta, 'Situação na Receita', (e[1] || 'não informada') + (e[2] ? ' desde ' + data(e[2]) : ''));
    if (e[3]) rotulo(meta, 'Aberta em', data(e[3]));
    if (e[6]) rotulo(meta, 'Sede', e[6]);
    pai.appendChild(meta);
    if (e[4]) pai.appendChild(el('p', 'meta', e[4] + (e[7] ? ' · microempreendedor individual' : '')));
    var tot = el('p', 'meta');
    rotulo(tot, 'Contratos com o município', String(e[10]));
    rotulo(tot, 'Total', moeda.format(e[9]));
    pai.appendChild(tot);
    if (e[8].length) {
      var ul = el('ul', 'socios');
      e[8].forEach(function (s) {
        var li = el('li');
        li.appendChild(el('b', null, s[0]));
        li.appendChild(document.createTextNode(' · ' + (s[1] || '') + (s[2] ? ' desde ' + data(s[2]) : '') + (s[5] ? ' · representante: ' + s[5] : '')));
        ul.appendChild(li);
      });
      pai.appendChild(ul);
    } else {
      pai.appendChild(el('p', 'meta', 'A Receita não informa quadro de sócios para esta empresa.'));
    }
  }
  function detalheEmpresa(k) {
    var d = el('details', 'emp');
    d.appendChild(el('summary', null, 'Empresa e sócios'));
    d.addEventListener('toggle', function () {
      if (d.open && d.childNodes.length === 1) quadroEmpresa(k, d);
    });
    return d;
  }

  // Licitação: [órgão, modalidade, número, ano, objeto, valor, tipo do valor, situação, data, participantes, vencedores, link]
  function cartaoLic(r) {
    var li = el('li', 'res');
    var topo = el('div', 'topo');
    topo.appendChild(el('span', 'id', (D.mods[r[1]] || r[1]) + ' ' + r[2] + ' · ' + D.org[r[0]]));
    topo.appendChild(chip(r[7]));
    li.appendChild(topo);
    li.appendChild(el('p', 'obj', r[4]));
    var meta = el('p', 'meta');
    if (r[5] !== null) rotulo(meta, r[6] === 'h' ? 'Valor homologado' : 'Valor estimado', moeda.format(r[5]));
    if (r[8]) rotulo(meta, 'Data', data(r[8]));
    if (r[9]) rotulo(meta, 'Participantes', String(r[9]));
    li.appendChild(meta);
    if (r[10]) { var v = el('p', 'meta'); rotulo(v, 'Quem ganhou', r[10]); li.appendChild(v); }
    if (r[11]) li.appendChild(link(D.base_lic, r[11], 'Ver documentos no TCE-RS'));
    if (r[12] && r[12].length) li.appendChild(detalheEmpresa(r[12][0]));
    return li;
  }

  // Contrato: [órgão, número, ano, instrumento, fornecedor, documento, objeto, valor inicial, valor atual, aditivos, acréscimo de quantidade, assinatura, fim, modalidade, link]
  function cartaoCon(r) {
    var li = el('li', 'res');
    var topo = el('div', 'topo');
    topo.appendChild(el('span', 'id', r[3] + ' ' + r[1] + ' · ' + D.org[r[0]] + (r[13] ? ' · ' + (D.mods[r[13]] || r[13]) : '')));
    var vigente = r[12] && r[12] >= D.hoje;
    topo.appendChild(el('span', 'chip ' + (vigente ? 'ok' : 'info'), vigente ? 'Em vigor até ' + data(r[12]) : (r[12] ? 'Terminou em ' + data(r[12]) : 'Vigência não informada')));
    li.appendChild(topo);
    li.appendChild(el('p', 'obj', r[6]));
    var meta = el('p', 'meta');
    if (r[4]) rotulo(meta, 'Fornecedor', r[4] + (r[5] ? ' (' + r[5] + ')' : ''));
    li.appendChild(meta);
    var val = el('p', 'meta');
    rotulo(val, 'Valor inicial', moeda.format(r[7]));
    if (r[8] !== r[7]) rotulo(val, 'Valor com aditivos', moeda.format(r[8]));
    if (r[9]) rotulo(val, 'Aditivos', String(r[9]));
    if (r[11]) rotulo(val, 'Assinado em', data(r[11]));
    li.appendChild(val);
    if (r[14]) li.appendChild(link(D.base_con, r[14], 'Ver documentos no TCE-RS'));
    if (r[15]) li.appendChild(detalheEmpresa(r[15]));
    return li;
  }

  function cartaoEmp(k) {
    var e = D.emp[k];
    var li = el('li', 'res');
    var topo = el('div', 'topo');
    topo.appendChild(el('span', 'id', cnpjFmt(k)));
    topo.appendChild(el('span', 'chip ' + (e[1] === 'ATIVA' ? 'ok' : 'falta'), e[1] || 'Situação não informada'));
    li.appendChild(topo);
    li.appendChild(el('p', 'obj', e[0]));
    quadroEmpresa(k, li);
    return li;
  }

  function filtrar(tipo) {
    if (tipo === 'emp') {
      var qe = sem($('e-q').value), se = $('e-sit').value, qd = qe.replace(/\D/g, '');
      return D.chaves_emp.filter(function (k) {
        return (!se || D.emp[k][1] === se) && (!qe || D.busca_emp[k].indexOf(qe) >= 0 || (qd.length >= 5 && k.indexOf(qd) >= 0));
      });
    }
    if (tipo === 'lic') {
      var q = sem($('l-q').value), ano = $('l-ano').value, grupo = $('l-grupo').value, sit = $('l-sit').value, org = $('l-org').value;
      var lista = D.lic.filter(function (r, i) {
        return (!ano || String(r[3]) === ano) && (!org || String(r[0]) === org) &&
          (!grupo || D.grupo[r[1]] === grupo) && (!sit || r[7] === sit) && (!q || D.busca_lic[i].indexOf(q) >= 0);
      });
      if ($('l-ordem').value === 'valor') lista.sort(function (a, b) { return (b[5] || 0) - (a[5] || 0); });
      return lista;
    }
    var q2 = sem($('c-q').value), ano2 = $('c-ano').value, org2 = $('c-org').value, vig = $('c-vig').checked;
    var lista2 = D.con.filter(function (r, i) {
      return (!ano2 || String(r[2]) === ano2) && (!org2 || String(r[0]) === org2) &&
        (!vig || (r[12] && r[12] >= D.hoje)) && (!q2 || D.busca_con[i].indexOf(q2) >= 0);
    });
    if ($('c-ordem').value === 'valor') lista2.sort(function (a, b) { return b[8] - a[8]; });
    return lista2;
  }

  function mostrar(tipo) {
    var lista = filtrar(tipo);
    if (tipo === 'emp') {
      $('e-conta').textContent = lista.length.toLocaleString('pt-BR') + ' empresas';
      $('e-res').textContent = '';
      var fe = document.createDocumentFragment();
      lista.slice(0, estado.emp * POR_PAGINA).forEach(function (k) { fe.appendChild(cartaoEmp(k)); });
      $('e-res').appendChild(fe);
      $('e-mais').hidden = lista.length <= estado.emp * POR_PAGINA;
      return;
    }
    var alvo = $(tipo === 'lic' ? 'l-res' : 'c-res');
    var conta = $(tipo === 'lic' ? 'l-conta' : 'c-conta');
    var mais = $(tipo === 'lic' ? 'l-mais' : 'c-mais');
    var total = lista.reduce(function (s, r) { return s + ((tipo === 'lic' ? r[5] : r[8]) || 0); }, 0);
    conta.textContent = lista.length.toLocaleString('pt-BR') + (tipo === 'lic' ? ' processos' : ' contratos') +
      ' · ' + moeda.format(total) + (tipo === 'lic' ? ' somando os valores mostrados' : ' somando os valores com aditivos');
    alvo.textContent = '';
    var frag = document.createDocumentFragment();
    lista.slice(0, estado[tipo] * POR_PAGINA).forEach(function (r) { frag.appendChild(tipo === 'lic' ? cartaoLic(r) : cartaoCon(r)); });
    alvo.appendChild(frag);
    mais.hidden = lista.length <= estado[tipo] * POR_PAGINA;
  }

  function opcoes(sel, valores) {
    valores.forEach(function (v) { var o = el('option', null, v); o.value = v; sel.appendChild(o); });
  }

  function ligar(tipo, ids) {
    var espera;
    ids.forEach(function (id) {
      $(id).addEventListener(id.slice(2) === 'q' ? 'input' : 'change', function () {
        clearTimeout(espera);
        espera = setTimeout(function () { estado[tipo] = 1; mostrar(tipo); }, 180);
      });
    });
    $({ lic: 'l-mais', con: 'c-mais', emp: 'e-mais' }[tipo]).addEventListener('click', function () { estado[tipo] += 1; mostrar(tipo); });
  }

  fetch('compras-dados.json').then(function (r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function (dados) {
    D = dados;
    D.busca_lic = D.lic.map(function (r) { return sem(r[4] + ' ' + (r[10] || '') + ' ' + r[2] + ' ' + (D.mods[r[1]] || '')); });
    D.busca_con = D.con.map(function (r) { return sem(r[6] + ' ' + (r[4] || '') + ' ' + r[1]); });
    D.emp = D.emp || {};
    D.busca_emp = {};
    D.chaves_emp = Object.keys(D.emp).sort(function (a, b) { return D.emp[b][9] - D.emp[a][9]; });
    D.chaves_emp.forEach(function (k) {
      D.busca_emp[k] = sem(D.emp[k][0] + ' ' + D.emp[k][8].map(function (s) { return s[0] + ' ' + (s[5] || ''); }).join(' '));
    });
    var anosL = Array.from(new Set(D.lic.map(function (r) { return String(r[3]); }))).sort().reverse();
    var anosC = Array.from(new Set(D.con.map(function (r) { return String(r[2]); }))).sort().reverse();
    opcoes($('l-ano'), anosL);
    opcoes($('c-ano'), anosC);
    document.querySelectorAll('.filtros').forEach(function (f) { f.hidden = false; });
    ligar('lic', ['l-q', 'l-ano', 'l-grupo', 'l-sit', 'l-org', 'l-ordem']);
    ligar('con', ['c-q', 'c-ano', 'c-org', 'c-vig', 'c-ordem']);
    mostrar('lic');
    mostrar('con');
    if ($('e-q')) { ligar('emp', ['e-q', 'e-sit']); mostrar('emp'); }
  }).catch(function () {
    ['l-conta', 'c-conta', 'e-conta'].forEach(function (id) {
      if (!$(id)) return;
      $(id).textContent = 'Não foi possível carregar a busca completa agora. As publicações mais recentes aparecem abaixo.';
    });
  });
})();
