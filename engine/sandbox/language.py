"""Small scoring language. Candidate AST is interpreted, never exec/eval'd.

Only the operations below exist; Python objects, imports and arbitrary method
dispatch are not part of this language. This is not general Python/NumPy.
This module uses only the standard library so workers need no site packages.
"""
import ast
import math
import operator

BUILTINS = {'abs', 'min', 'max', 'sum', 'len', 'range', 'enumerate', 'zip',
            'sorted', 'float', 'int', 'round', 'list', 'dict', 'tuple', 'set',
            'bool', 'str', 'all', 'any', 'HeuristicResult'}
ATTRS = {'current_location', 'candidate_stops', 'distance_matrix', 'partial_route',
         'shape', 'fill', 'setflags', 'get', 'items', 'keys', 'values',
         'sqrt', 'abs', 'min', 'max', 'sum', 'mean', 'isfinite', 'clip', 'linalg', 'norm'}
NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
         ast.AugAssign, ast.Expr, ast.For, ast.While, ast.If, ast.Break, ast.Continue,
         ast.Pass, ast.Name, ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict,
         ast.Subscript, ast.Slice, ast.Attribute, ast.Call, ast.keyword, ast.BinOp,
         ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.ListComp, ast.SetComp,
         ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.Load, ast.Store,
         ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
         ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt,
         ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)


def check_tree(tree, function_name):
    errors = []
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return ['Scoring language requires exactly one function']
    fn = tree.body[0]
    if fn.name != function_name:
        errors.append('Function name mismatch')
    args = fn.args
    if (len(args.args) != 1 or args.posonlyargs or args.vararg or args.kwarg
            or args.kwonlyargs or args.defaults or fn.decorator_list or fn.returns
            or args.args[0].annotation):
        errors.append('Use one unannotated context argument; no decorators or defaults')
    for node in ast.walk(tree):
        if not isinstance(node, NODES):
            errors.append(f'Unsupported scoring syntax: {type(node).__name__}')
        if isinstance(node, ast.FunctionDef) and node is not fn:
            errors.append('Nested functions are unsupported')
        if isinstance(node, ast.Name) and node.id.startswith('_'):
            errors.append('Private names are unsupported')
        if isinstance(node, ast.Attribute) and node.attr not in ATTRS:
            errors.append(f'Unsupported scoring attribute: {node.attr}')
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in BUILTINS:
                    errors.append(f'Unsupported scoring call: {node.func.id}')
            elif not isinstance(node.func, ast.Attribute):
                errors.append('Indirect calls are unsupported')
            if any(k.arg is None for k in node.keywords):
                errors.append('Keyword expansion is unsupported')
        if isinstance(node, ast.comprehension) and node.is_async:
            errors.append('Async comprehensions are unsupported')
    return errors


class Matrix:
    def __init__(self, rows):
        self.rows = rows
        self.writable = False

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, key):
        if isinstance(key, tuple):
            row, col = key
            if isinstance(row, slice):
                return [r[col] for r in self.rows[row]]
            return self.rows[row][col]
        return tuple(self.rows[key]) if isinstance(key, int) else self.rows[key]

    def __setitem__(self, key, value):
        if not self.writable:
            raise ValueError('assignment destination is read-only')
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError('Only scalar matrix assignment is supported')
        self.rows[key[0]][key[1]] = value


class Context:
    def __init__(self, data):
        self.fields = {**data, 'distance_matrix': Matrix(data['distance_matrix'])}


class Returned(Exception):
    def __init__(self, value):
        self.value = value


class BreakLoop(Exception):
    pass


class ContinueLoop(Exception):
    pass


class Interpreter:
    MAX_ITEMS = 50000
    OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
    CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
           ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
           ast.Is: operator.is_, ast.IsNot: operator.is_not}

    def __init__(self):
        self.steps = 0

    def tick(self):
        self.steps += 1
        if self.steps > 2_000_000:
            raise TimeoutError('Scoring operation budget timeout')

    def bounded(self, value):
        if isinstance(value, (list, tuple, dict, set, str)) and len(value) > self.MAX_ITEMS:
            raise TimeoutError('Scoring allocation budget timeout')
        if isinstance(value, int) and value.bit_length() > 4096:
            raise TimeoutError('Scoring integer budget timeout')
        return value

    def binary(self, op, left, right):
        if isinstance(op, ast.Pow) and (abs(right) > 1024 or abs(left) > 1e100):
            raise TimeoutError('Scoring power budget timeout')
        if isinstance(op, ast.Mult):
            for seq, count in ((left, right), (right, left)):
                if isinstance(seq, (list, tuple, str)) and isinstance(count, int):
                    if len(seq) * count > self.MAX_ITEMS:
                        raise TimeoutError('Scoring allocation budget timeout')
        return self.bounded(self.OPS[type(op)](left, right))

    def assign(self, target, value, env):
        if isinstance(target, ast.Name):
            env[target.id] = self.bounded(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            if len(target.elts) != len(value):
                raise ValueError('Unpacking length mismatch')
            for key, val in zip(target.elts, value):
                self.assign(key, val, env)
        elif isinstance(target, ast.Subscript):
            obj = self.expr(target.value, env)
            if not isinstance(obj, (dict, list, Matrix)):
                raise ValueError('Unsupported assignment target')
            obj[self.expr(target.slice, env)] = value
            self.bounded(obj)
        else:
            raise ValueError('Attribute assignment is unsupported')

    def block(self, nodes, env):
        for node in nodes:
            self.tick()
            if isinstance(node, ast.Return):
                raise Returned(self.expr(node.value, env) if node.value else None)
            elif isinstance(node, ast.Assign):
                value = self.expr(node.value, env)
                for target in node.targets:
                    self.assign(target, value, env)
            elif isinstance(node, ast.AugAssign):
                self.assign(node.target, self.binary(node.op, self.expr(node.target, env), self.expr(node.value, env)), env)
            elif isinstance(node, ast.Expr):
                self.expr(node.value, env)
            elif isinstance(node, ast.If):
                self.block(node.body if self.expr(node.test, env) else node.orelse, env)
            elif isinstance(node, (ast.For, ast.While)):
                iterator = iter(self.expr(node.iter, env)) if isinstance(node, ast.For) else None
                broken = False
                while True:
                    self.tick()
                    if iterator is not None:
                        try:
                            self.assign(node.target, next(iterator), env)
                        except StopIteration:
                            break
                    elif not self.expr(node.test, env):
                        break
                    try:
                        self.block(node.body, env)
                    except ContinueLoop:
                        continue
                    except BreakLoop:
                        broken = True
                        break
                if not broken:
                    self.block(node.orelse, env)
            elif isinstance(node, ast.Break):
                raise BreakLoop()
            elif isinstance(node, ast.Continue):
                raise ContinueLoop()
            elif not isinstance(node, ast.Pass):
                raise ValueError(f'Unsupported statement: {type(node).__name__}')

    def comprehension(self, node, env):
        values = []
        def visit(index, scope):
            self.tick()
            if index == len(node.generators):
                values.append((self.expr(node.key, scope), self.expr(node.value, scope))
                              if isinstance(node, ast.DictComp) else self.expr(node.elt, scope))
                self.bounded(values)
                return
            gen = node.generators[index]
            for item in self.expr(gen.iter, scope):
                self.tick()
                self.assign(gen.target, item, scope)
                if all(self.expr(test, scope) for test in gen.ifs):
                    visit(index + 1, scope.copy())
        visit(0, env.copy())
        return dict(values) if isinstance(node, ast.DictComp) else set(values) if isinstance(node, ast.SetComp) else values

    def expr(self, node, env):
        self.tick()
        if isinstance(node, ast.Constant):
            return self.bounded(node.value)
        if isinstance(node, ast.Name):
            return env[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self.expr(n, env) for n in node.elts]
            return tuple(values) if isinstance(node, ast.Tuple) else set(values) if isinstance(node, ast.Set) else values
        if isinstance(node, ast.Dict):
            return {self.expr(k, env): self.expr(v, env) for k, v in zip(node.keys, node.values)}
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return self.comprehension(node, env)
        if isinstance(node, ast.Slice):
            return slice(*(self.expr(n, env) if n else None for n in (node.lower, node.upper, node.step)))
        if isinstance(node, ast.Subscript):
            return self.expr(node.value, env)[self.expr(node.slice, env)]
        if isinstance(node, ast.Attribute):
            obj = self.expr(node.value, env)
            if isinstance(obj, Context) and node.attr in obj.fields:
                return obj.fields[node.attr]
            if isinstance(obj, Matrix) and node.attr == 'shape':
                return (len(obj.rows), len(obj.rows[0]))
            raise ValueError('Attribute is not a readable scoring value')
        if isinstance(node, ast.BinOp):
            return self.binary(node.op, self.expr(node.left, env), self.expr(node.right, env))
        if isinstance(node, ast.UnaryOp):
            value = self.expr(node.operand, env)
            return {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}[type(node.op)](value)
        if isinstance(node, ast.BoolOp):
            value = self.expr(node.values[0], env)
            for part in node.values[1:]:
                if (isinstance(node.op, ast.And) and not value) or (isinstance(node.op, ast.Or) and value):
                    break
                value = self.expr(part, env)
            return value
        if isinstance(node, ast.Compare):
            left = self.expr(node.left, env)
            for op, part in zip(node.ops, node.comparators):
                right = self.expr(part, env)
                if not self.CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self.expr(node.body if self.expr(node.test, env) else node.orelse, env)
        if isinstance(node, ast.Call):
            args = [self.expr(n, env) for n in node.args]
            kwargs = {k.arg: self.expr(k.value, env) for k in node.keywords}
            if isinstance(node.func, ast.Name):
                import builtins
                if node.func.id == 'HeuristicResult':
                    return {'scores': kwargs['scores']}
                if node.func.id not in BUILTINS:
                    raise ValueError('Unsupported call')
                # Only trusted built-ins from this literal allowlist, never env.
                return self.bounded(getattr(builtins, node.func.id)(*args, **kwargs))
            attr = node.func.attr
            # Numerical scalar compatibility only; never expose a NumPy module.
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'np':
                funcs = {'sqrt': math.sqrt, 'abs': abs, 'min': min, 'max': max,
                         'sum': sum, 'mean': lambda x: sum(x) / len(x),
                         'isfinite': math.isfinite, 'clip': lambda x, a, b: min(max(x, a), b)}
                if attr not in funcs:
                    raise ValueError('Unsupported NumPy operation')
                return funcs[attr](*args, **kwargs)
            obj = self.expr(node.func.value, env)
            if isinstance(obj, dict) and attr in ('get', 'items', 'keys', 'values'):
                return getattr(obj, attr)(*args, **kwargs)
            if isinstance(obj, Matrix) and attr == 'setflags':
                obj.writable = bool(kwargs.get('write', args[0] if args else False))
                return None
            if isinstance(obj, Matrix) and attr == 'fill':
                if not obj.writable:
                    raise ValueError('assignment destination is read-only')
                for row in obj.rows:
                    row[:] = [args[0]] * len(row)
                return None
            raise ValueError('Unsupported scoring method')
        raise ValueError(f'Unsupported expression: {type(node).__name__}')

    def run(self, source, name, context):
        tree = ast.parse(source)
        errors = check_tree(tree, name)
        if errors:
            raise ValueError('; '.join(errors))
        fn = tree.body[0]
        try:
            self.block(fn.body, {fn.args.args[0].arg: Context(context)})
        except Returned as result:
            return result.value
        return None
