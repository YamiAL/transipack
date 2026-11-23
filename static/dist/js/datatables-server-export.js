(function () {
  var exportUrl = window.DATATABLE_SERVER_EXPORT_URL;
  if (!exportUrl) {
    return;
  }

  function csrfToken() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    if (match) {
      return decodeURIComponent(match[1]);
    }
    var input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
  }

  function cellText(node) {
    if (!node) {
      return '';
    }
    return (node.innerText || node.textContent || '')
      .replace(/\u00a0/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function closest(element, selector) {
    if (element.closest) {
      return element.closest(selector);
    }
    while (element && element.nodeType === 1) {
      if (element.matches && element.matches(selector)) {
        return element;
      }
      element = element.parentElement;
    }
    return null;
  }

  function collectFromWrapper(button) {
    var wrapper = closest(button, '.dataTables_wrapper') || closest(button, '.content');
    var table = wrapper ? wrapper.querySelector('table') : document.querySelector('table');
    if (!table) {
      return null;
    }

    var headers = [];
    var headerCells = table.tHead ? table.tHead.querySelectorAll('tr:last-child th, tr:last-child td') : [];
    for (var i = 0; i < headerCells.length; i++) {
      headers.push(cellText(headerCells[i]));
    }

    var rows = [];
    var bodyRows = table.tBodies.length ? table.tBodies[0].rows : [];
    for (var r = 0; r < bodyRows.length; r++) {
      var row = [];
      var cells = bodyRows[r].cells;
      for (var c = 0; c < cells.length; c++) {
        row.push(cellText(cells[c]));
      }
      rows.push(row);
    }

    var footer = [];
    if (table.tFoot) {
      var footerCells = table.tFoot.querySelectorAll('tr:last-child th, tr:last-child td');
      for (var f = 0; f < footerCells.length; f++) {
        footer.push(cellText(footerCells[f]));
      }
    }

    return { headers: headers, rows: rows, footer: footer };
  }

  function formatFromButton(button) {
    var className = ' ' + (button.className || '') + ' ';
    if (className.indexOf(' buttons-excel ') !== -1) {
      return 'xlsx';
    }
    if (className.indexOf(' buttons-csv ') !== -1) {
      return 'csv';
    }
    if (className.indexOf(' buttons-pdf ') !== -1) {
      return 'pdf';
    }
    return null;
  }

  function download(format, payload) {
    payload.format = format;
    payload.title = payload.title || document.title || 'Exportacion';
    fetch(exportUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken()
      },
      body: JSON.stringify(payload)
    }).then(function (response) {
      if (!response.ok) {
        throw new Error('No se pudo exportar el documento.');
      }
      var disposition = response.headers.get('Content-Disposition') || '';
      var filenameMatch = /filename="?([^"]+)"?/.exec(disposition);
      var filename = filenameMatch ? filenameMatch[1] : ('exportacion.' + format);
      return response.blob().then(function (blob) {
        var url = window.URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      });
    }).catch(function () {
      window.alert('No se pudo exportar el documento.');
    });
  }

  document.addEventListener('click', function (event) {
    try {
      var button = closest(event.target, 'a.buttons-excel, a.buttons-csv, a.buttons-pdf, button.buttons-excel, button.buttons-csv, button.buttons-pdf');
      if (!button) {
        return;
      }
      if ((button.className || '').indexOf('buttons-print') !== -1 || (button.className || '').indexOf('buttons-copy') !== -1) {
        return;
      }
      var format = formatFromButton(button);
      if (!format) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      var payload = collectFromWrapper(button);
      if (!payload || !payload.headers.length) {
        window.alert('No hay datos para exportar.');
        return;
      }
      download(format, payload);
    } catch (err) {
      return;
    }
  }, true);
})();
