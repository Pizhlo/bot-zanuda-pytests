# Для тестирования максимальной длины
def generate_long_string(length: int, char: str = "a") -> str:
    return char * length


ALPHABET = 52


# Для тестирования с разными символами
def generate_test_string(length: int) -> str:
    import string

    characters = []
    for index in range(length):
        char_index = index % ALPHABET
        characters.append(string.ascii_letters[char_index])

    return "".join(characters)
