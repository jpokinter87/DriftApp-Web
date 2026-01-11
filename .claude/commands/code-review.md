---
description: Review de code complete avec refactoring selon les principes fondamentaux
category: utilities-debugging
argument-hint: fichier(s) ou repertoire a analyser
---

# Code Review et Refactoring - Principes Fondamentaux

Review de code exhaustive avec refactoring selon les meilleures pratiques de programmation.

## Instructions

Tu vas effectuer une review de code complete et proposer un refactoring : **$ARGUMENTS**

---

## PHASE 1 : ANALYSE PRELIMINAIRE

### 1.1 Identification du Code

Avant toute analyse, identifie :

```python
# Informations a collecter
- Fichier(s) concerne(s)
- Langage et version
- Framework/bibliotheques utilisees
- Contexte fonctionnel (que fait ce code?)
- Tests existants (couverture)
- Documentation existante
```

### 1.2 Metriques de Base

Calcule les metriques initiales :

```bash
# Pour Python
# Nombre de lignes
wc -l <fichier>

# Complexite cyclomatique (si radon disponible)
radon cc <fichier> -a

# Maintenabilite
radon mi <fichier>

# Lignes de code vs commentaires
radon raw <fichier>
```

---

## PHASE 2 : VERIFICATION DES PRINCIPES SOLID

### 2.1 Single Responsibility Principle (SRP)

**Regle** : Une classe/fonction ne doit avoir qu'une seule raison de changer.

**Checklist** :
- [ ] Chaque classe a une responsabilite unique et clairement definie
- [ ] Chaque fonction fait une seule chose
- [ ] Le nom de la classe/fonction decrit exactement ce qu'elle fait
- [ ] Pas de "and" dans le nom (ex: `validateAndSave` = 2 responsabilites)

**Code Smell** :
```python
# MAUVAIS - Multiple responsabilites
class UserManager:
    def create_user(self, data): ...
    def send_email(self, user): ...      # Responsabilite email
    def generate_report(self, user): ... # Responsabilite reporting
    def validate_data(self, data): ...   # Responsabilite validation

# BON - Responsabilite unique
class UserRepository:
    def create(self, user): ...
    def find_by_id(self, id): ...

class EmailService:
    def send(self, recipient, message): ...

class UserValidator:
    def validate(self, data): ...
```

### 2.2 Open/Closed Principle (OCP)

**Regle** : Ouvert a l'extension, ferme a la modification.

**Checklist** :
- [ ] Nouvelles fonctionnalites ajoutables sans modifier le code existant
- [ ] Utilisation de l'heritage ou composition pour etendre
- [ ] Pas de switch/if-else sur des types pour choisir un comportement

**Code Smell** :
```python
# MAUVAIS - Modification requise pour chaque nouveau type
def calculate_area(shape):
    if shape.type == "circle":
        return 3.14 * shape.radius ** 2
    elif shape.type == "rectangle":
        return shape.width * shape.height
    # Ajouter un nouveau type = modifier cette fonction

# BON - Extension sans modification
class Shape(ABC):
    @abstractmethod
    def area(self) -> float: ...

class Circle(Shape):
    def area(self) -> float:
        return 3.14 * self.radius ** 2

class Rectangle(Shape):
    def area(self) -> float:
        return self.width * self.height
```

### 2.3 Liskov Substitution Principle (LSP)

**Regle** : Les sous-classes doivent etre substituables a leurs classes parentes.

**Checklist** :
- [ ] Une sous-classe peut remplacer sa classe parente sans casser le code
- [ ] Les preconditions ne sont pas renforcees dans les sous-classes
- [ ] Les postconditions ne sont pas affaiblies dans les sous-classes
- [ ] Les invariants de la classe parente sont preserves

**Code Smell** :
```python
# MAUVAIS - Viole LSP (un carre n'est pas un rectangle substituable)
class Rectangle:
    def set_width(self, w): self.width = w
    def set_height(self, h): self.height = h

class Square(Rectangle):
    def set_width(self, w):
        self.width = self.height = w  # Comportement different!

# BON - Hierarchie correcte
class Shape(ABC):
    @abstractmethod
    def area(self) -> float: ...

class Rectangle(Shape): ...
class Square(Shape): ...  # Pas d'heritage Rectangle
```

### 2.4 Interface Segregation Principle (ISP)

**Regle** : Pas d'interface trop large; plusieurs interfaces specifiques.

**Checklist** :
- [ ] Les interfaces sont petites et specifiques
- [ ] Les classes n'implementent pas de methodes inutiles
- [ ] Pas de methodes vides ou levant NotImplementedError

**Code Smell** :
```python
# MAUVAIS - Interface trop large
class Worker(ABC):
    @abstractmethod
    def work(self): ...
    @abstractmethod
    def eat(self): ...  # Un robot ne mange pas!

class Robot(Worker):
    def work(self): ...
    def eat(self): raise NotImplementedError  # Violation!

# BON - Interfaces segregees
class Workable(ABC):
    @abstractmethod
    def work(self): ...

class Eatable(ABC):
    @abstractmethod
    def eat(self): ...

class Human(Workable, Eatable): ...
class Robot(Workable): ...  # N'implemente que ce qui est necessaire
```

### 2.5 Dependency Inversion Principle (DIP)

**Regle** : Dependre des abstractions, pas des implementations concretes.

**Checklist** :
- [ ] Les modules de haut niveau ne dependent pas des modules de bas niveau
- [ ] Les deux dependent d'abstractions
- [ ] Injection de dependances utilisee
- [ ] Pas d'instanciation directe de dependances dans les classes

**Code Smell** :
```python
# MAUVAIS - Dependance concrete
class OrderService:
    def __init__(self):
        self.db = MySQLDatabase()  # Couplage fort!
        self.mailer = SMTPMailer()  # Couplage fort!

# BON - Injection de dependances
class OrderService:
    def __init__(self, db: Database, mailer: Mailer):
        self.db = db      # Abstraction
        self.mailer = mailer  # Abstraction
```

---

## PHASE 3 : PRINCIPES COMPLEMENTAIRES

### 3.1 DRY (Don't Repeat Yourself)

**Checklist** :
- [ ] Pas de code duplique (copier-coller)
- [ ] Logique commune extraite dans des fonctions/classes
- [ ] Constantes definies une seule fois
- [ ] Configuration centralisee

**Detection** :
```bash
# Chercher du code similaire
# Analyser les patterns repetes
grep -rn "pattern" .
```

**Refactoring** :
```python
# MAUVAIS - Duplication
def process_user(user):
    if not user.email or '@' not in user.email:
        raise ValueError("Invalid email")
    # ...

def process_admin(admin):
    if not admin.email or '@' not in admin.email:  # Duplique!
        raise ValueError("Invalid email")
    # ...

# BON - Extraction
def validate_email(email: str) -> bool:
    return email and '@' in email

def process_user(user):
    if not validate_email(user.email):
        raise ValueError("Invalid email")
```

### 3.2 KISS (Keep It Simple, Stupid)

**Checklist** :
- [ ] Solution la plus simple qui fonctionne
- [ ] Pas de sur-ingenierie
- [ ] Code lisible sans commentaires excessifs
- [ ] Eviter les abstractions prematurees

**Code Smell** :
```python
# MAUVAIS - Sur-ingenierie
class AbstractFactoryBuilderStrategyManager:
    # 500 lignes pour faire quelque chose de simple...

# BON - Simple et direct
def get_config(key: str) -> str:
    return os.environ.get(key, defaults.get(key))
```

### 3.3 YAGNI (You Aren't Gonna Need It)

**Checklist** :
- [ ] Pas de code "au cas ou"
- [ ] Pas de fonctionnalites non demandees
- [ ] Pas de parametres inutilises
- [ ] Pas de classes/methodes jamais appelees

**Detection** :
```bash
# Trouver le code mort
# Chercher les imports inutilises
# Chercher les fonctions jamais appelees
```

### 3.4 Separation of Concerns (SoC)

**Checklist** :
- [ ] Logique metier separee de la presentation
- [ ] Acces aux donnees isole
- [ ] Configuration separee du code
- [ ] Couches bien definies (controller, service, repository)

---

## PHASE 4 : CLEAN CODE

### 4.1 Nommage

**Regles** :
- [ ] Noms revelateurs d'intention
- [ ] Noms prononcables et searchables
- [ ] Pas d'abreviations cryptiques
- [ ] Conventions respectees (snake_case Python, camelCase JS)

```python
# MAUVAIS
def calc(d, t):
    return d / t

# BON
def calculate_speed(distance_km: float, time_hours: float) -> float:
    return distance_km / time_hours
```

### 4.2 Fonctions

**Regles** :
- [ ] Petites (< 20 lignes idealement)
- [ ] Font une seule chose
- [ ] Un seul niveau d'abstraction
- [ ] Peu d'arguments (< 3 idealement)
- [ ] Pas d'effets de bord caches

```python
# MAUVAIS - Trop longue, multiple responsabilites
def process_order(order):
    # 100 lignes de validation, calcul, sauvegarde, email...

# BON - Decomposee
def process_order(order):
    validated_order = validate_order(order)
    calculated_order = calculate_totals(validated_order)
    saved_order = save_order(calculated_order)
    notify_customer(saved_order)
    return saved_order
```

### 4.3 Commentaires

**Regles** :
- [ ] Le code doit etre auto-documentant
- [ ] Commentaires pour le "pourquoi", pas le "quoi"
- [ ] Pas de code commente (utiliser git)
- [ ] Docstrings pour API publiques

```python
# MAUVAIS
# Incremente i de 1
i = i + 1

# BON
# Compense le decalage d'index 0-based de l'API externe
i = i + 1
```

### 4.4 Gestion des Erreurs

**Regles** :
- [ ] Exceptions plutot que codes de retour
- [ ] Exceptions specifiques (pas de catch-all)
- [ ] Messages d'erreur informatifs
- [ ] Fail fast (echouer tot)

```python
# MAUVAIS
def divide(a, b):
    try:
        return a / b
    except:  # Catch-all!
        return None  # Erreur silencieuse!

# BON
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError(f"Cannot divide {a} by zero")
    return a / b
```

---

## PHASE 5 : CODE SMELLS A DETECTER

### 5.1 Smells de Code

| Smell | Description | Solution |
|-------|-------------|----------|
| **Long Method** | Fonction > 20 lignes | Extraire en sous-fonctions |
| **Large Class** | Classe avec trop de responsabilites | Diviser en classes |
| **Long Parameter List** | > 3 parametres | Objet parametre ou builder |
| **Divergent Change** | Classe modifiee pour raisons differentes | Separer les responsabilites |
| **Shotgun Surgery** | Un changement = modifications multiples | Consolider la logique |
| **Feature Envy** | Methode utilise plus une autre classe | Deplacer la methode |
| **Data Clumps** | Groupes de donnees toujours ensemble | Creer une classe |
| **Primitive Obsession** | Primitifs au lieu d'objets | Value Objects |
| **Switch Statements** | Switch sur types | Polymorphisme |
| **Parallel Inheritance** | Hierarchies paralleles | Fusionner ou deleguer |
| **Lazy Class** | Classe qui ne fait presque rien | Supprimer ou fusionner |
| **Speculative Generality** | Code "au cas ou" | Supprimer (YAGNI) |
| **Temporary Field** | Champs parfois null | Extraire classe ou Null Object |
| **Message Chains** | a.b().c().d() | Delegation |
| **Middle Man** | Classe qui delegue tout | Supprimer intermediaire |
| **Inappropriate Intimacy** | Classes trop couplees | Deplacer methodes/champs |
| **Comments** | Commentaires excessifs | Refactorer le code |
| **Dead Code** | Code jamais execute | Supprimer |
| **Magic Numbers** | Valeurs hardcodees | Constantes nommees |

### 5.2 Detection Automatique

```python
# Verifications a effectuer

# 1. Longueur des fonctions
def check_function_length(func):
    lines = len(inspect.getsourcelines(func)[0])
    if lines > 20:
        return f"Warning: {func.__name__} has {lines} lines (recommended < 20)"

# 2. Nombre de parametres
def check_parameters(func):
    sig = inspect.signature(func)
    params = len(sig.parameters)
    if params > 3:
        return f"Warning: {func.__name__} has {params} parameters (recommended < 4)"

# 3. Complexite cyclomatique
def check_complexity(func):
    # Compter les if, for, while, and, or, except
    # Score > 10 = trop complexe
    pass

# 4. Couplage
def check_coupling(cls):
    # Compter les imports et dependances
    # Score eleve = couplage fort
    pass
```

---

## PHASE 6 : SECURITE

### 6.1 Checklist Securite

- [ ] Pas d'injection SQL (utiliser parametres)
- [ ] Pas d'injection de commandes (echapper les inputs)
- [ ] Validation des entrees utilisateur
- [ ] Pas de secrets dans le code (utiliser env vars)
- [ ] Gestion securisee des mots de passe (hash)
- [ ] Protection CSRF/XSS pour le web
- [ ] Principe du moindre privilege
- [ ] Logs sans donnees sensibles

```python
# MAUVAIS - Injection SQL
query = f"SELECT * FROM users WHERE id = {user_id}"

# BON - Parametres
query = "SELECT * FROM users WHERE id = %s"
cursor.execute(query, (user_id,))

# MAUVAIS - Secret dans le code
API_KEY = "sk-1234567890abcdef"

# BON - Variable d'environnement
API_KEY = os.environ.get("API_KEY")
```

---

## PHASE 7 : PERFORMANCE

### 7.1 Checklist Performance

- [ ] Pas de requetes N+1 (eager loading)
- [ ] Pas de calculs redondants (memoization)
- [ ] Structures de donnees appropriees
- [ ] Algorithmes optimaux (complexite)
- [ ] Pas de fuites memoire
- [ ] Lazy loading quand approprie

```python
# MAUVAIS - N+1 queries
for user in users:
    orders = db.query(f"SELECT * FROM orders WHERE user_id = {user.id}")

# BON - Eager loading
users_with_orders = db.query("""
    SELECT u.*, o.* FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
""")

# MAUVAIS - Calcul redondant
def fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)  # Exponentiel!

# BON - Memoization
@lru_cache(maxsize=None)
def fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)  # Lineaire
```

---

## PHASE 8 : TESTS

### 8.1 Checklist Tests

- [ ] Couverture adequate (> 80% pour code critique)
- [ ] Tests unitaires pour logique metier
- [ ] Tests d'integration pour interfaces
- [ ] Tests isoles (pas de dependances externes)
- [ ] Tests rapides (< 1s unitaire)
- [ ] Nommage clair: `test_<method>_<scenario>_<expected>`

```python
# BON - Test bien structure
class TestUserValidator:
    def test_validate_email_with_valid_email_returns_true(self):
        validator = UserValidator()
        result = validator.validate_email("user@example.com")
        assert result is True

    def test_validate_email_with_missing_at_raises_error(self):
        validator = UserValidator()
        with pytest.raises(ValidationError):
            validator.validate_email("invalid-email")
```

### 8.2 Patterns de Test

- **AAA** : Arrange, Act, Assert
- **Given-When-Then** : Pour BDD
- **Test Doubles** : Mock, Stub, Fake, Spy

---

## PHASE 9 : RAPPORT DE REVIEW

### Template de Rapport

```markdown
# Code Review Report

## Informations
- **Fichier(s)**: [fichiers analyses]
- **Date**: [date]
- **Revieweur**: Claude

## Resume Executif
- **Score Global**: X/10
- **Problemes Critiques**: X
- **Problemes Majeurs**: X
- **Problemes Mineurs**: X
- **Suggestions**: X

## Metriques
| Metrique | Valeur | Cible | Status |
|----------|--------|-------|--------|
| Lignes de code | X | - | - |
| Complexite cyclomatique | X | < 10 | OK/NOK |
| Couverture tests | X% | > 80% | OK/NOK |
| Duplication | X% | < 5% | OK/NOK |

## Violations SOLID
### SRP
- [ ] ...

### OCP
- [ ] ...

(etc.)

## Code Smells Detectes
1. **[Smell]** dans `fichier:ligne`
   - Description: ...
   - Impact: ...
   - Solution: ...

## Problemes de Securite
1. ...

## Problemes de Performance
1. ...

## Refactoring Propose

### Priorite Haute
1. ...

### Priorite Moyenne
1. ...

### Priorite Basse
1. ...

## Code Refactore

(Proposer le code refactore avec explications)
```

---

## PHASE 10 : EXECUTION DU REFACTORING

### 10.1 Processus

1. **Sauvegarder l'etat actuel**
   ```bash
   git checkout -b refactor/code-review
   ```

2. **Ecrire/verifier les tests AVANT refactoring**
   ```bash
   pytest --cov=<module> tests/
   ```

3. **Refactorer incrementalement**
   - Un changement a la fois
   - Tester apres chaque changement
   - Commiter frequemment

4. **Verifier la non-regression**
   ```bash
   pytest -v
   ```

5. **Mesurer l'amelioration**
   - Comparer les metriques avant/apres
   - Verifier la couverture maintenue

### 10.2 Techniques de Refactoring

| Technique | Quand l'utiliser |
|-----------|------------------|
| Extract Method | Fonction trop longue |
| Extract Class | Classe avec trop de responsabilites |
| Move Method | Methode dans mauvaise classe |
| Rename | Nom pas clair |
| Replace Temp with Query | Variable temporaire reutilisee |
| Introduce Parameter Object | Trop de parametres |
| Replace Conditional with Polymorphism | Switch sur types |
| Introduce Null Object | Checks null repetes |
| Extract Interface | Pour decouplage |
| Pull Up / Push Down | Reorganiser hierarchie |

---

## EXECUTION

Maintenant, analyse le code specifie (**$ARGUMENTS**) en suivant toutes ces phases :

1. Lis et comprends le code
2. Identifie les violations de chaque principe
3. Detecte les code smells
4. Verifie securite et performance
5. Genere le rapport complet
6. Propose le refactoring avec code

Sois exhaustif mais pragmatique : priorise les problemes par impact.
