import xml.etree.ElementTree as ET
import json

# Узел дерева
class TreeNode:
    def __init__(self, tag, parent=None, index=0, children=None, text_value=None):
        self.tag = tag  # Название тега
        self.parent = parent  # Родительский узел
        self.index = index    # Индекс среди детей родителя
        self.children = children if children is not None else []  # Дочерние узлы
        self.text_value = text_value  # Содержимое для узлов типа mi, mn и mo

def sklon(word, is_genitive):
    genitive_map = {
        'отношение': 'отношения',
        'корень': 'корня',
        'сумма': 'суммы',
        'разность': 'разности',
        'произведение': 'произведения',
        'частное': 'частного',
    }
    if is_genitive:
        return genitive_map.get(word, word)
    else:
        return word

def mathml_to_tree(node, parent=None, index=0):
    tag = node.tag.split('}')[-1]  # Убираем namespace

    # Если это узел типа mi, mn или mo, сохраняем текстовое значение
    if tag in {"mi", "mn", "mo"}:
        text_value = node.text
    else:
        text_value = None

    if not list(node):  # Если нет дочерних элементов
        return TreeNode(tag=tag, parent=parent, index=index, text_value=text_value)

    children = []
    for i, child in enumerate(node):
        child_node = mathml_to_tree(child, parent=node, index=i)
        children.append(child_node)
    
    # Объединяем последовательные mi/mn только внутри mrow и mfenced
    if tag in {'mrow', 'mfenced'}:
        merged_children = []
        i = 0
        while i < len(children):
            if children[i].tag in {'mi', 'mn'}:
                merged_text = children[i].text_value or ''
                j = i + 1
                while j < len(children) and children[j].tag in {'mi', 'mn'}:
                    merged_text += children[j].text_value or ''
                    j += 1
                merged_node = TreeNode(tag='mn', parent=None, index=len(merged_children), children=[], text_value=merged_text)
                merged_children.append(merged_node)
                i = j
            else:
                merged_children.append(children[i])
                i +=1
    else:
        merged_children = children

    # Если среди операторов есть знаки сравнения, делим на левый и правый mrow
    comparison_symbols = {'=', '>', '<', '≥', '≤', '\\geqslant', '\\leqslant'}
    # Ищем оператор сравнения на верхнем уровне
    comp_index = None
    for i, ch in enumerate(merged_children):
        if ch.tag == 'mo' and ch.text_value in comparison_symbols:
            comp_index = i
            break

    if comp_index is not None and tag == 'math':
        # Создаем левый mrow
        left_children = merged_children[:comp_index]
        right_children = merged_children[comp_index+1:]
        comp_node = merged_children[comp_index]

        left_mrow = TreeNode('mrow', parent=None, index=0, children=left_children, text_value=None)
        for idx, c in enumerate(left_children):
            c.parent = left_mrow
            c.index = idx

        right_mrow = TreeNode('mrow', parent=None, index=2, children=right_children, text_value=None)
        for idx, c in enumerate(right_children):
            c.parent = right_mrow
            c.index = idx

        new_children = []
        if left_children:
            left_mrow.parent = None
            new_children.append(left_mrow)
        new_children.append(comp_node)
        if right_children:
            right_mrow.parent = None
            new_children.append(right_mrow)

        merged_children = new_children

    # Теперь установим правильные ссылки на родителя и индексы
    current_node = TreeNode(tag=tag, parent=parent, index=index, children=merged_children, text_value=text_value)
    for idx, child in enumerate(merged_children):
        child.parent = current_node
        child.index = idx
    return current_node

def build_tree_from_mathml(mathml_str):
    root = ET.fromstring(mathml_str)
    return mathml_to_tree(root, parent=None, index=0)

def describe_tree(tree, is_first_call=True):
    if not tree:
        return ""
    
    is_genitive = not is_first_call

    op_map = {
        '+': 'сумма',
        '-': 'разность',
        '−': 'разность',
        '⋅': 'произведение',
        '*': 'произведение',
        '·': 'произведение',
        '/': 'частное',
        '=': 'равно',
        '>': 'больше',
        '<': 'меньше',
        '≥': 'больше или равно',
        '≤': 'меньше или равно',
        '∑': 'сумма'
    }

    comparison_symbols = {'=', '>', '<', '≥', '≤', '\\geqslant', '\\leqslant'}

    if len(tree.children) >= 3:
        descriptions = []
        for i in range(len(tree.children) - 2):
            triplet = tree.children[i:i+3]
            if triplet[1].tag == "mo" and triplet[1].text_value not in comparison_symbols and triplet[1].text_value != '∑':
                operator_symbol = triplet[1].text_value
                operand1 = describe_tree(triplet[0], is_first_call=False)
                operand2 = describe_tree(triplet[2], is_first_call=False)
                operator_word = op_map.get(operator_symbol, f"операция {operator_symbol}")
                operator_word = sklon(operator_word, is_genitive)
                description = f"{operator_word} {operand1} и {operand2}"
                descriptions.append(description)
        if descriptions:
            result = "; ".join(descriptions)
            return result

    def describe_munderover(children, is_first):
        sum_symbol = children[0]
        lower = children[1]
        upper = children[2]

        var_name = ""
        lower_bound = ""
        if lower.children and len(lower.children) >= 3:
            lower_bound = "по " + "".join(describe_tree(child, is_first_call=False) for child in lower.children) if children else ""

        upper_bound = ""
        if upper.children and len(upper.children) >= 1:
            upper_bound = "до " + describe_tree(upper.children[0], is_first_call=False)

        return f"{describe_tree(sum_symbol, is_first_call=False)} {lower_bound} {upper_bound} от "

    rules = {
        "mfrac": lambda children: f"{sklon('отношение', is_genitive)} {describe_tree(children[0], is_first_call=False)} и {describe_tree(children[1], is_first_call=False)}",
        "msup": lambda children: (
            f"{describe_tree(children[0], is_first_call=False)} в квадрате" if describe_tree(children[1], is_first_call=False) == "2" else
            f"{describe_tree(children[0], is_first_call=False)} в кубе" if describe_tree(children[1], is_first_call=False) == "3" else
            f"{describe_tree(children[0], is_first_call=False)} в степени {describe_tree(children[1], is_first_call=False)}"
        ),
        "msqrt": lambda children: f"{sklon('корень', is_genitive)} из {describe_tree(children[0], is_first_call=False)}",
        "munderover": lambda children: describe_munderover(children, False),
        "msubsup": lambda children: describe_munderover(children, False),
        "mi": lambda children: str(tree.text_value) if tree.text_value else "неизвестная переменная",
        "mn": lambda children: str(tree.text_value) if tree.text_value else "неизвестное число",
        "mo": lambda children: (
            f" {op_map.get(tree.text_value, ' ? ')} "  if tree.text_value in comparison_symbols else
            ('сумма' if tree.text_value == '∑' else ('интеграл' if tree.text_value == '∫' else(
                tree.text_value if tree.index == 0 else
                f"{sklon(op_map.get(tree.text_value, f'операция {tree.text_value}'), is_genitive)} {describe_tree(children[0], is_first_call=False)} и {describe_tree(children[1], is_first_call=False)}"
                if len(children) == 2 else f"{sklon(op_map.get(tree.text_value, f'операция {tree.text_value}'), is_genitive)}"
            )))
        ),
        "mrow": lambda children: "".join(describe_tree(child, is_first_call=False) for child in children) if children else "",
        "mfenced": lambda children: "(" + " ".join(describe_tree(child, is_first_call=False) for child in children) + ")" if children else "()",
        "math": lambda children: "".join(describe_tree(child, is_first_call=True) for child in children) if children else "",
    }
    
    rule = rules.get(tree.tag)
    if rule:
        result = rule(tree.children) if tree.children else rule([])
        return result
    return "неизвестный тег"

def print_tree(node, level=0):
    indent = "  " * level
    parent_info = f"{node.parent.tag} (index={node.index})" if node.parent else "None"
    children_tags = [child.tag for child in node.children]
    print(f"{indent}Tag: {node.tag}")
    print(f"{indent}Text Value: {node.text_value}")
    print(f"{indent}Children: {children_tags}")
    print(f"{indent}Parent: {parent_info}")
    print(f"{indent}Index: {node.index}")
    print()
    for child in node.children:
        print_tree(child, level + 1)

import json

with open('dataset.json', 'r', encoding='utf-8') as f:
    dataset = json.load(f)

# Для каждой записи в датасете
i = 0
for entry in dataset:
    i += 1
    mathml_str = entry['mathml']
    expected_descr = entry['description']
    tree = build_tree_from_mathml(mathml_str)
    description = describe_tree(tree)
    print(f"{i}) MathML: {mathml_str}")
    print(f"Ожидаемое описание: \t {expected_descr}")
    print(f"Описание: \t\t {description}")
    print()
