import os
from pathlib import Path
from lxml import etree

from justai import Agent, set_prompt_file, get_prompt
from dotenv import load_dotenv

from cache import cached


class Translator(Agent):

    def __init__(self):
        super().__init__(os.environ.get('OPENAI_MODEL', 'gpt-4-turbo-preview'), temperature=0, max_tokens=4096)
        set_prompt_file(Path(__file__).parent / 'prompts.toml')
        self.system_message = get_prompt('SYSTEM')
        self.xml = ''
        self.version = ''

    def load(self, input_file: str | Path):
        # Input bestaat uit <transunit> elementen. Die hebben een datatype property.
        # Binnen elke <transunit> zit een <source> element en komt (na vertaling) een <target> element.
        # ALs datatype == "plaintext" dan zit de te vertalen tekst direct in de <source>
        # Als datatype == "x-DocumentState" dan zit er in de <source> een <g> element met daarin de te vertalen tekst.

        # In 2.0:
        # Input bestaat uit <unit> elementen. Die hebben een Id.
        # Binnen elke <unit> zit een <segment> en daarin een <source>
        # In de source zit ofwel direct tekst, ofwel een <pc> element
        # met daarin nog een <pc> element met daarin de te vertalen tekst
        with open(input_file, 'r') as f:
            self.xml = f.read()
        try:
            self.version = self.xml.split('xliff:document:')[1].split('"')[0].split("'")[0]
        except IndexError:
            raise ValueError(f'No XLIFF version found in {input_file}')
        if self.version not in ['1.2', '2.0']:
            raise ValueError(f'{input_file} has an unsupported XLIFF version: {self.version}')

    def translate(self, language: str) -> str:
        if self.version == '1.2':
            return self.translate1_2(language)
        elif self.version == '2.0':
            return self.translate2_0(language)

    def translate1_2(self, language):
        # XML-data laden met lxml
        parser = etree.XMLParser(ns_clean=True)
        root = etree.fromstring(self.xml.encode('utf-8'), parser=parser)
        namespaces = {'ns': 'urn:oasis:names:tc:xliff:document:1.2'}

        # Verzamel alle te vertalen teksten en hun paden
        texts_to_translate = []

        # Start het verzamelproces vanuit <source> elementen en vertaal de teksten
        for trans_unit in root.xpath('.//ns:trans-unit', namespaces=namespaces):
            source = trans_unit.xpath('.//ns:source', namespaces=namespaces)[0]
            texts_to_translate.extend(collect_texts_from_element(source))

        # Vertaal met AI
        translated_texts = self.do_translate(texts_to_translate, language)

        # Plaats vertaalde teksten terug in nieuwe <target> elementen met behoud van structuur
        counter = [0]
        for trans_unit in root.xpath('.//ns:trans-unit', namespaces=namespaces):
            source = trans_unit.xpath('.//ns:source', namespaces=namespaces)[0]
            target = etree.Element(namespaces['ns'] + 'target')
            copy_structure_with_texts(source, target, translated_texts, counter)
            trans_unit.append(target)

        # De bijgewerkte XLIFF-structuur omzetten naar een string en afdrukken
        updated_xml = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8').decode('utf-8')
        return updated_xml

    def translate2_0(self, language):
        # XML-data laden met lxml
        parser = etree.XMLParser(ns_clean=True)
        root = etree.fromstring(self.xml.encode('utf-8'), parser=parser)
        namespaces = {'ns': 'urn:oasis:names:tc:xliff:document:2.0'}

        # Verzamel alle te vertalen teksten en hun paden
        texts_to_translate = []

        # Start het verzamelproces vanuit <source> elementen en vertaal de teksten
        for source in root.xpath('.//ns:source', namespaces=namespaces):
            texts_to_translate.extend(collect_texts_from_element(source))

        # Vertaal met AI
        translated_texts = self.do_translate(texts_to_translate, language)

        # Plaats vertaalde teksten terug in nieuwe <target> elementen met behoud van structuur
        counter = [0]
        for segment in root.xpath('.//ns:segment', namespaces=namespaces):
            source = segment.xpath('.//ns:source', namespaces=namespaces)[0]
            target = etree.SubElement(segment, namespaces['ns'] + 'target')
            copy_structure_with_texts(source, target, translated_texts, counter)

        # De bijgewerkte XLIFF-structuur omzetten naar een string en afdrukken
        updated_xml = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8').decode('utf-8')
        return updated_xml

    def do_translate(self, texts, language: str):
        @cached
        def run_prompt(prompt: str):
            return self.chat(prompt, return_json=False)

        # TODO: translate_str stap voor stap opbouwen tot ie over de 3000 tokens gaat.
        #  Dan prompt, toevoegen aan translations en repeat
        source_list = list(set([text for text in texts if is_translatable(text)]))  # Filter out doubles
        source_str = '\n'.join([f'{index + 1} [[{text}]]' for index, text in enumerate(source_list)])
        prompt = get_prompt('TRANSLATE', language=language, translate_str=source_str, count=len(source_list))
        prompt_result = run_prompt(prompt)
        target_list = [t.split(']]')[0] for t in prompt_result.split('[[')[1:]]
        translation_dict = dict(zip(source_list, target_list))
        translations = [translation_dict.get(text, text) for text in texts]
        return translations


def collect_texts_from_element(element):
    texts = []
    if element.text and element.text.strip():
        texts.append(element.text.strip())
    for child in element:
        texts.extend(collect_texts_from_element(child))
    return texts


def copy_structure_with_texts(source, target, translated_texts, counter=[0]):
    """ Kopieer de structuur van <source> naar <target> en behoud de teksten """
    if source.text and source.text.strip():
        try:
            target.text = translated_texts[counter[0]]
            counter[0] += 1
        except IndexError:
            print('IndexError')
    for child in source:
        child_copy = etree.SubElement(target, child.tag, attrib=child.attrib)
        copy_structure_with_texts(child, child_copy, translated_texts, counter)


def is_translatable(text) -> bool:
    """ Returns True if the unit should be translated """
    return text and len(text.strip()) > 1 and text[0] != '%'


if __name__ == "__main__":
    load_dotenv()

    def run_test(input_file: [Path | str], language: str):
        if isinstance(input_file, str):
            input_file = Path(input_file)
        tr = Translator()
        try:
            tr.load(input_file)
        except ValueError as e:
            print(e.args[0])
            return
        translated = tr.translate(language)
        outfile = f'{input_file.stem} {language}.xlf'
        with open(outfile, 'w') as f:
            f.write(translated)
        print(outfile)

    run_test('AI_2.1.xlf', 'Oekraïens')
    run_test('short 1.2.xlf', 'Pools')
    run_test('Proefbestand 2.0.xlf', 'Engels')