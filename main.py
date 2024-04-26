import os
from pathlib import Path
import re
import time
from xml.dom.minidom import parseString

from dotenv import load_dotenv
from justai import Translator
from justai.translator.translator import parse_xliff_with_unit_clusters, StringCache

USE_CACHE = False


def language_code(language):
    languages = {
        "Bulgaars": "bg-BG",
        "Duits": "de-DE",
        "Engels": "en-GB",
        "Frans": "fr-FR",
        "Grieks": "el-GR",
        "Italiaans": "it-IT",
        "Nederlands": "nl-NL",
        "Oekraïens": "uk-UA",
        "Pools": "pl-PL",
        "Portugees": "pt-PT",
        "Roemeens": "ro-RO",
        "Russisch": "ru-RU",
        "Spaans": "es-ES"
    }
    return languages.get(language, None)  # Retourneert None als de taal niet gevonden is.


def run_test(input_file: [Path | str], language: str, use_clusters=False):
    if not USE_CACHE:
        StringCache(language).clear()

    if isinstance(input_file, str):
        input_file = Path(input_file)
    key = os.environ["ANTHROPIC_API_KEY_AUTONIVEAU"]
    key = os.environ["ANTHROPIC_API_KEY"]
    tr = Translator(None, ANTHROPIC_API_KEY=key)
    tr.system = """Je bent een vertaler. Je vertaalt educatieve software die is bedoeld voor het trainen van automonteurs. 
    Alle teksten gaan dus ook over de werking van auto's en het vak van automonteur."""
    tokens_in = tolkens_out = word_count = 0
    if use_clusters:
        with open(input_file, 'r') as f:
            xliff_content = f.read()
        result = parse_xliff_with_unit_clusters(xliff_content, 20000)
        header = result['header']
        clusters = result['units']
        footer = result['footer']
        xliff_version = result['version']
        translated = ''
        for index, cluster in enumerate(clusters):
            #if index != 2:
            #    continue # !!
            tr.read(header + cluster + footer)
            translated_cluster = tr.translate(language, string_cached=USE_CACHE)
            tokens_in += tr.input_token_count
            tolkens_out += tr.output_token_count
            word_count += tr.word_count

            if xliff_version == '2.0':
                xliff_without_header_and_footer_match = re.search(r'<unit[\s\S]*<\/unit>', translated_cluster)
            else:
                xliff_without_header_and_footer_match = re.search(r'<trans-unit[\s\S]*<\/trans-unit>',
                                                                  translated_cluster)

            # Controleer of er een match gevonden is en voeg deze toe aan translated_units
            if xliff_without_header_and_footer_match:
                translated_cluster = xliff_without_header_and_footer_match.group(0)
                translated += translated_cluster

        # In geval van XLIFF 2.0, voeg de target language (trgLang) toe aan de header.
        if xliff_version == "2.0":
            lang_code = language_code(language)
            # Vervang om trgLang="en-GB" of een andere taalcode, zoals nl-NL, in de header te zetten.
            header = re.sub(r'(<xliff [^>]*)(>)', r'\1 trgLang="{}"\2'.format(lang_code), header)

        translated = header + translated + footer
    else:
        try:
            tr.load(input_file)
        except ValueError as e:
            print(e.args[0])
            return
        translated = tr.translate(language)
    outfile = f'{input_file.parent}/{input_file.stem} {language}.xlf'
    with open(outfile, 'w') as f:
        f.write(translated)
    outfile = f'{input_file.parent}/{input_file.stem} {language}.xml'
    with open(outfile, 'w') as f:
        f.write('\n'.join([l for l in parseString(translated).toprettyxml(indent="  ").split('\n') if l.strip()]))
    print('Tokens in', tokens_in)
    print('Tokens out', tolkens_out)
    print('Word count', word_count)

INPUTS = {1: 'TR 5234 Diagnose Motormanagement en Aandrijflijn 2023.xlf',
          2: 'AI E2 test document.xlf',
          3: "_HP's test document.xlf",
          4: 'AI_2.1.xlf',
          5: 'test5.xml',
          6: 'Veilig werken bij Emoss BJ 24.3.xlf'}


def inp(no: int):
    global INPUTS
    return Path('input') / INPUTS[no]


if __name__ == "__main__":
    load_dotenv()
    start = time.time()

    run_test(inp(3), 'Nederlands', use_clusters=True)

    print(f'Duration: {time.time() - start:.2f} seconds')
