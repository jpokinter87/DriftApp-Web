// Page Configuration (chantier B) — formulaire accordéon auto-généré.
// Charge {schema, values} depuis /api/configuration/, édite localement, POST au save.

function getCookie(name) {
  const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return m ? m.pop() : '';
}

function deepGet(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function deepSet(obj, path, value) {
  const keys = path.split('.');
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (typeof cur[keys[i]] !== 'object' || cur[keys[i]] === null) cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = value;
}

function configPage() {
  return {
    schema: [],
    values: {},
    open: {},
    dirty: false,
    saving: false,
    loading: true,
    error: '',
    notice: '',

    get normalSections() { return this.schema.filter((s) => !s.advanced); },
    get advancedSections() { return this.schema.filter((s) => s.advanced); },

    async load() {
      try {
        const resp = await fetch('/api/configuration/');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const body = await resp.json();
        this.schema = body.schema;
        this.values = body.values;
        // Toutes les sections fermées par défaut — ouvertes seulement au clic.
        this.schema.forEach((s) => { this.open[s.key] = false; });
        this.open['__advanced__'] = false;
      } catch (e) {
        this.error = 'Impossible de charger la configuration : ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    toggle(key) { this.open[key] = !this.open[key]; },

    lastGroup(section, field) {
      // Renvoie le group du champ précédent pour n'afficher l'en-tête qu'au changement.
      const idx = section.fields.indexOf(field);
      return idx > 0 ? section.fields[idx - 1].group : null;
    },

    renderField(field) {
      const val = deepGet(this.values, field.path);
      const help = field.help
        ? `<span class="cfg-help" title="${field.help.replace(/"/g, '&quot;')}">ⓘ</span>`
        : '';
      const label = `<span class="cfg-label">${field.label}${help}</span>`;
      const onChange = `onchange="window.__configSet('${field.path}', this, '${field.type}')"`;
      let input;
      if (field.type === 'bool') {
        input = `<input type="checkbox" class="cfg-input" style="flex:none;width:auto" ${val ? 'checked' : ''} ${onChange}>`;
      } else if (field.enum) {
        const opts = field.enum
          .map((o) => `<option value="${o}" ${o === val ? 'selected' : ''}>${o}</option>`)
          .join('');
        input = `<select class="cfg-input" ${onChange}>${opts}</select>`;
      } else if (field.type === 'int' || field.type === 'float') {
        const step = field.type === 'int' ? '1' : 'any';
        input = `<input type="number" step="${step}" class="cfg-input" value="${val}" ${onChange}>`;
      } else {
        const safe = (val == null ? '' : String(val)).replace(/"/g, '&quot;');
        input = `<input type="text" class="cfg-input" value="${safe}" ${onChange}>`;
      }
      return label + input;
    },

    async save() {
      this.saving = true;
      this.notice = '';
      this.error = '';
      try {
        const resp = await fetch('/api/configuration/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify(this.values),
        });
        const body = await resp.json();
        if (!resp.ok) {
          this.error = body.path ? `${body.error} (${body.path})` : body.error || 'Erreur';
          return;
        }
        this.notice = body.message || 'Configuration enregistrée — redémarrage requis.';
        this.dirty = false;
      } catch (e) {
        this.error = 'Échec de la sauvegarde : ' + e.message;
      } finally {
        this.saving = false;
      }
    },

    init() {
      // Pont pour les inputs rendus via x-html (hors portée Alpine).
      window.__configSet = (path, el, type) => {
        let v;
        if (type === 'bool') v = el.checked;
        else if (type === 'int') v = parseInt(el.value, 10);
        else if (type === 'float') v = parseFloat(el.value);
        else v = el.value;
        if ((type === 'int' || type === 'float') && Number.isNaN(v)) v = el.value; // laisse le backend rejeter
        deepSet(this.values, path, v);
        this.dirty = true;
        this.notice = '';
      };
    },
  };
}
