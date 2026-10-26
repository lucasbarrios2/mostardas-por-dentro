(function () {
  // Dica do gráfico: só complementa; os valores já estão na barra e na tabela.
  var grafico = document.querySelector('.grafico');
  var tip = document.getElementById('tip');
  if (grafico && tip) {
    function mostrar(row, x, y) {
      tip.textContent = '';
      var forte = document.createElement('strong');
      forte.textContent = row.getAttribute('data-val');
      tip.appendChild(forte);
      tip.appendChild(document.createTextNode(row.querySelector('.bar-label').textContent + ' · ' + row.getAttribute('data-share')));
      tip.appendChild(document.createElement('br'));
      tip.appendChild(document.createTextNode(row.getAttribute('data-pc')));
      tip.hidden = false;
      var caixa = grafico.getBoundingClientRect();
      var esquerda = Math.min(Math.max(8, x - caixa.left + 14), grafico.clientWidth - tip.offsetWidth - 8);
      tip.style.left = esquerda + 'px';
      tip.style.top = (y - caixa.top + 18) + 'px';
    }
    function esconder() { tip.hidden = true; }
    grafico.querySelectorAll('.bar-row').forEach(function (row) {
      row.addEventListener('pointermove', function (e) { mostrar(row, e.clientX, e.clientY); });
      row.addEventListener('pointerleave', esconder);
      row.addEventListener('focus', function () {
        var r = row.getBoundingClientRect();
        mostrar(row, r.left + r.width / 2, r.bottom - 4);
      });
      row.addEventListener('blur', esconder);
    });
  }

  // Copiar a pergunta pronta para o e-SIC.
  document.querySelectorAll('.copiar').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var alvo = document.getElementById(btn.getAttribute('data-alvo'));
      if (!alvo) return;
      function selecionar() {
        var sel = window.getSelection();
        var range = document.createRange();
        range.selectNodeContents(alvo);
        sel.removeAllRanges();
        sel.addRange(range);
        btn.textContent = 'Texto selecionado: copie com Ctrl+C';
      }
      try {
        navigator.clipboard.writeText(alvo.textContent.trim()).then(function () {
          btn.textContent = 'Pergunta copiada';
          setTimeout(function () { btn.textContent = 'Copiar pergunta'; }, 2500);
        }, selecionar);
      } catch (e) { selecionar(); }
    });
  });
})();
