# -*- coding: utf-8 -*-

# External imports
import json
import logging
import os.path
import re
import sys

# Internal imports (if any)


_SIMPLE_MECHANICS = {u'Charge', u'Stealth', u'Windfury', u'Taunt', u'Divine Shield'}
_HTML_TAG_PAT = re.compile(r'</?[^>]+>')
_LOGGER = logging.getLogger('hearthpricer.json_loader')


def _parse_text(card):
    mechanics = set(card.get(u'mechanics', list()))
    text = card.pop(u'text', None)
    if text is not None:
        # Remove presentation characters.
        clean_text = _HTML_TAG_PAT.sub('', text).replace('\n', ' ')
        clean_text = re.sub(r'[ ]+', ' ', clean_text)
        # Remove the simple mechanics from the text (they will appear in the card mechanics as well).
        for simple_mechanic in _SIMPLE_MECHANICS:
            if simple_mechanic in mechanics:
                clean_text = clean_text.replace(simple_mechanic, '')
        # Remove . from text literals (will be the mechanic separator) to avoid problems.
        clean_text = clean_text.replace('."', '"')
        # Remove leading/trailing characters
        clean_text = clean_text.strip(' .,')
        if clean_text:
            text_mechanics = [x for x in (x.strip() for x in clean_text.split('.')) if x]
        else:
            text_mechanics = list()
    else:
        text_mechanics = list()
    text_mechanics = [x for x in text_mechanics
                      if not x.startswith(u'Battlecry:') and not x.startswith(u'Deathrattle:')]
    card[u'text_mechanics'] = text_mechanics


def _process_card(card):
    type_ = card.pop('type')
    if type_ != 'Minion':
        _LOGGER.debug('\t\tUnsupported type "{}"'.format(type_))
        return None

    _parse_text(card)

    mechanics = set(card.pop(u'mechanics', list()))
    if not _SIMPLE_MECHANICS.issuperset(mechanics):
        _LOGGER.debug('\t\tUnsupported mechanics {}'.format(mechanics.difference(_SIMPLE_MECHANICS)))
        return None

    for simple_mechanic in _SIMPLE_MECHANICS:
        card[simple_mechanic.lower()] = 0

    attack = card[u'attack']
    health = card[u'health']

    # Windfury
    if u'Windfury' in mechanics:
        card[u'windfury'] = attack
    # Charge
    if u'Charge' in mechanics:
        card[u'charge'] = attack + card[u'windfury']
    # Stealth
    if u'Stealth' in mechanics:
        card[u'stealth'] = 1
    # Taunt
    if u'Taunt' in mechanics:
        card[u'taunt'] = health
    # Divine Shield
    if u'Divine Shield' in mechanics:
        card[u'divine shield'] = 1

    return card


def _process_cards(cards, include_class_cards=True):
    _LOGGER.debug('Processing cards...')
    processed_cards = list()
    for card in cards:
        if 'playerClass' in card:
            if not include_class_cards:
                continue
            del card['playerClass']
        name = card['name']
        _LOGGER.debug('\tProcessing "{}"...'.format(name))
        card = _process_card(card)
        if card is None:
            continue
        text_mechanics = card.pop('text_mechanics', list())
        if text_mechanics:
            _LOGGER.debug('\t\tUnsupported mechanics {}'.format(text_mechanics))
        else:
            processed_cards.append(card)
    return processed_cards


def load(filename, include_class_cards=True):
    if sys.version_info.major == 2:
        with open(filename) as fp:
            all_card_sets = json.load(fp, encoding='utf-8')
    else:
        with open(filename, encoding='utf-8') as fp:
            all_card_sets = json.load(fp)

    all_cards = sum((v for k, v in all_card_sets.items()
                     if k not in ('Debug', 'Credits', 'Missions', 'System')), list())
    # Select only collectible cards
    all_collectible_cards = (card for card in all_cards
                             if 'collectible' in card and card['collectible'])
    # Remove heroes
    all_collectible_cards = (card for card in all_collectible_cards
                             if 'type' in card and card['type'] != 'Hero')
    # Only interested in these tags for pricer purposes
    interest_tags = ('attack', 'cost', 'durability', 'health', 'mechanics', 'name', 'playerClass', 'text',
                     'type')
    all_collectible_cards = ({k: v for k, v in card.items() if k in interest_tags}
                             for card in all_collectible_cards)
    return _process_cards(all_collectible_cards, include_class_cards=include_class_cards)


if __name__ == '__main__':
    all_sets_filename = os.path.join(os.path.dirname(__file__), '..', 'data', 'AllSets.json')

    # # Uncomment the following lines to update the date file
    # import urllib
    # urllib.urlretrieve ('http://hearthstonejson.com/json/AllSets.json', all_sets_filename)

    logging.basicConfig(level=logging.DEBUG)
    cards_list = load(all_sets_filename, include_class_cards=False)
    print('Total cards:', len(cards_list))
    print('Card keys:', ', '.join(set(sum((list(x.keys()) for x in cards_list), list()))))
