"""Test-only adapter for legacy fixture replies; not used by production code."""
from copy import deepcopy
from affiliate_link_ids import link_map


def as_link_ids(reply, source):
    def respond(prompt):
        data=deepcopy(reply(prompt))
        reverse={url:key for key,url in link_map(source()).items()}
        for product in data.get('products',[]):
            product['link_ids']=[reverse.get(url,'FORGED_LINK') for url in product.pop('affiliate_urls',[])]
        data['unassigned_link_ids']=[reverse.get(url,'FORGED_LINK') for url in data.pop('unassigned_urls',[])]
        return data
    return respond
