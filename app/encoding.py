def encode_set(tuple:tuple):
    res = ""
    for item in tuple:
        res += str(len(item)) + "/:" + item
    return res

def decode_set(str):
    decoded_strings = set()
    i = 0
    while i < len(str):
        delim = str.find('/:', i)
        length = int(str[i:delim])
        str_ = str[delim+2 : delim+2+length]
        decoded_strings.add(str_)
        i = delim + 2 + length
    return decoded_strings